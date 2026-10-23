package io.vectormatch.server;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.Unpooled;
import io.netty.channel.*;
import io.netty.channel.group.ChannelGroup;
import io.netty.channel.group.DefaultChannelGroup;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.http.*;
import io.netty.handler.codec.http.websocketx.*;
import io.netty.util.CharsetUtil;
import io.netty.util.concurrent.GlobalEventExecutor;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;

/** Loopback-only executable workbench. It does not advertise replicated execution. */
public final class WorkbenchServer implements AutoCloseable {
    private final ObjectMapper mapper = new ObjectMapper();
    private final EventLoopGroup acceptor = new NioEventLoopGroup(1);
    private final EventLoopGroup workers = new NioEventLoopGroup(2);
    private final ChannelGroup sockets = new DefaultChannelGroup(GlobalEventExecutor.INSTANCE);
    private final Workbench workbench;
    private final Path webRoot;
    private final AtomicBoolean closed = new AtomicBoolean();
    private Channel server;

    public WorkbenchServer(Path journal, Path webRoot) throws Exception {
        this.webRoot = webRoot.toAbsolutePath().normalize();
        this.workbench = new Workbench(journal, mapper);
        workbench.broadcaster(state -> {
            try {
                String json = mapper.writeValueAsString(Map.of("type", "state", "data", state));
                for (Channel socket : sockets) if (socket.isWritable()) socket.writeAndFlush(new TextWebSocketFrame(json));
            } catch (Exception error) { System.err.println("snapshot serialization failed: " + error.getMessage()); }
        });
    }

    public int start(int port) throws InterruptedException {
        server = new ServerBootstrap().group(acceptor, workers).channel(NioServerSocketChannel.class)
                .childOption(ChannelOption.TCP_NODELAY, true)
                .childOption(ChannelOption.WRITE_BUFFER_WATER_MARK, new WriteBufferWaterMark(32 * 1024, 128 * 1024))
                .childHandler(new ChannelInitializer<SocketChannel>() {
                    @Override protected void initChannel(SocketChannel channel) {
                        channel.pipeline().addLast(new HttpServerCodec(), new HttpObjectAggregator(16_384), new Handler());
                    }
                }).bind("127.0.0.1", port).sync().channel();
        return ((java.net.InetSocketAddress) server.localAddress()).getPort();
    }

    private final class Handler extends SimpleChannelInboundHandler<Object> {
        private WebSocketServerHandshaker handshaker;
        @Override protected void channelRead0(ChannelHandlerContext context, Object message) throws Exception {
            if (message instanceof FullHttpRequest request) handleHttp(context, request);
            else if (message instanceof CloseWebSocketFrame frame) {
                if (handshaker != null) handshaker.close(context.channel(), frame.retain());
                else context.close();
            } else if (message instanceof PingWebSocketFrame frame) {
                context.writeAndFlush(new PongWebSocketFrame(frame.content().retain()));
            } else if (message instanceof TextWebSocketFrame frame && frame.text().equals("ping")) {
                context.writeAndFlush(new TextWebSocketFrame("{\"type\":\"pong\"}"));
            }
        }

        private void handleHttp(ChannelHandlerContext context, FullHttpRequest request) throws Exception {
            boolean keepAlive = HttpUtil.isKeepAlive(request);
            if (!request.decoderResult().isSuccess()) { json(context, 400, Map.of("error", "invalid HTTP request"), false); return; }
            if (!allowed(request)) { json(context, 403, Map.of("error", "loopback same-origin access required"), false); return; }
            String path = new QueryStringDecoder(request.uri()).path();
            if (path.equals("/ws")) {
                WebSocketServerHandshakerFactory factory = new WebSocketServerHandshakerFactory(
                        "ws://" + request.headers().get(HttpHeaderNames.HOST) + "/ws", null, false, 4096);
                handshaker = factory.newHandshaker(request);
                if (handshaker == null) { WebSocketServerHandshakerFactory.sendUnsupportedVersionResponse(context.channel()); return; }
                handshaker.handshake(context.channel(), request).addListener(future -> {
                    if (future.isSuccess()) {
                        sockets.add(context.channel()); workbench.connections(sockets.size());
                        context.writeAndFlush(new TextWebSocketFrame(mapper.writeValueAsString(Map.of("type", "state", "data", workbench.state()))));
                    }
                });
                return;
            }
            if (request.method().equals(HttpMethod.GET) && path.equals("/api/state")) {
                json(context, 200, workbench.state(), keepAlive); return;
            }
            if (request.method().equals(HttpMethod.GET) && path.equals("/health")) {
                json(context, 200, workbench.state().get("health"), keepAlive); return;
            }
            if (request.method().equals(HttpMethod.GET) && path.equals("/metrics")) {
                json(context, 200, workbench.state().get("metrics"), keepAlive); return;
            }
            if (request.method().equals(HttpMethod.POST) && path.startsWith("/api/")) {
                CompletableFuture<Map<String, Object>> result;
                var input = request.content().isReadable() ? mapper.readTree(request.content().toString(CharsetUtil.UTF_8)) : mapper.createObjectNode();
                if (input == null || !input.isObject()) { json(context, 400, Map.of("error", "JSON object required"), keepAlive); return; }
                result = switch (path) {
                    case "/api/orders" -> workbench.place(input);
                    case "/api/cancel" -> workbench.cancel(input);
                    case "/api/control/flow" -> workbench.controlFlow(input);
                    case "/api/control/replay" -> workbench.verifyReplay();
                    default -> null;
                };
                if (result == null) { json(context, 404, Map.of("error", "route not found"), keepAlive); return; }
                result.whenComplete((value, error) -> context.executor().execute(() -> {
                    try {
                        if (error == null) json(context, 200, value, keepAlive);
                        else {
                            Throwable cause = error instanceof CompletionException ? error.getCause() : error;
                            int code = cause instanceof IllegalArgumentException ? 400 : cause instanceof RejectedExecutionException ? 429 : 503;
                            json(context, code, Map.of("error", cause.getMessage() == null ? "request failed" : cause.getMessage()), keepAlive);
                        }
                    } catch (Exception failure) { context.close(); }
                }));
                return;
            }
            if (request.method().equals(HttpMethod.GET) && !path.startsWith("/api/")) {
                Path file = webRoot.resolve(path.equals("/") ? "index.html" : path.substring(1)).normalize();
                if (!file.startsWith(webRoot)) { json(context, 403, Map.of("error", "invalid path"), false); return; }
                if (!Files.isRegularFile(file) && !path.contains(".")) file = webRoot.resolve("index.html");
                if (Files.isRegularFile(file) && Files.size(file) <= 8_388_608) {
                    byte[] content = Files.readAllBytes(file);
                    FullHttpResponse response = new DefaultFullHttpResponse(HttpVersion.HTTP_1_1, HttpResponseStatus.OK, Unpooled.wrappedBuffer(content));
                    String type = file.toString().endsWith(".js") ? "text/javascript" : file.toString().endsWith(".css") ? "text/css"
                            : file.toString().endsWith(".svg") ? "image/svg+xml" : "text/html";
                    response.headers().set(HttpHeaderNames.CONTENT_TYPE, type + "; charset=utf-8");
                    send(context, response, keepAlive); return;
                }
            }
            json(context, 404, Map.of("error", "not found; build web with npm run build"), keepAlive);
        }

        @Override public void channelInactive(ChannelHandlerContext context) throws Exception {
            sockets.remove(context.channel()); workbench.connections(sockets.size()); super.channelInactive(context);
        }
        @Override public void exceptionCaught(ChannelHandlerContext context, Throwable cause) {
            try { json(context, 400, Map.of("error", "invalid request"), false); }
            catch (Exception ignored) { context.close(); }
        }
    }

    private static boolean allowed(FullHttpRequest request) {
        try {
            String host = URI.create("http://" + request.headers().get(HttpHeaderNames.HOST, "")).getHost();
            if (!"localhost".equals(host) && !"127.0.0.1".equals(host)) return false;
            String origin = request.headers().get(HttpHeaderNames.ORIGIN);
            if (origin == null) return true;
            URI uri = URI.create(origin);
            return ("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                    && ("localhost".equals(uri.getHost()) || "127.0.0.1".equals(uri.getHost()));
        } catch (RuntimeException error) { return false; }
    }
    private void json(ChannelHandlerContext context, int status, Object value, boolean keepAlive) throws Exception {
        FullHttpResponse response = new DefaultFullHttpResponse(HttpVersion.HTTP_1_1, HttpResponseStatus.valueOf(status),
                Unpooled.wrappedBuffer(mapper.writeValueAsBytes(value)));
        response.headers().set(HttpHeaderNames.CONTENT_TYPE, "application/json; charset=utf-8");
        response.headers().set(HttpHeaderNames.CACHE_CONTROL, "no-store");
        send(context, response, keepAlive);
    }
    private static void send(ChannelHandlerContext context, FullHttpResponse response, boolean keepAlive) {
        response.headers().setInt(HttpHeaderNames.CONTENT_LENGTH, response.content().readableBytes());
        response.headers().set("X-Content-Type-Options", "nosniff");
        if (keepAlive) response.headers().set(HttpHeaderNames.CONNECTION, HttpHeaderValues.KEEP_ALIVE);
        ChannelFuture future = context.writeAndFlush(response);
        if (!keepAlive) future.addListener(ChannelFutureListener.CLOSE);
    }
    @Override public void close() throws Exception {
        if (!closed.compareAndSet(false, true)) return;
        if (server != null) server.close().syncUninterruptibly();
        sockets.close().awaitUninterruptibly();
        workbench.close();
        acceptor.shutdownGracefully().syncUninterruptibly(); workers.shutdownGracefully().syncUninterruptibly();
    }
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getProperty("vm.port", "8000"));
        Path runtime = Path.of(System.getProperty("vm.runtime", "runtime/workbench"));
        Path web = Path.of(System.getProperty("vm.web", "web/dist"));
        WorkbenchServer app = new WorkbenchServer(runtime.resolve("commands.vmj"), web);
        int bound = app.start(port);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try { app.close(); } catch (Exception error) { System.err.println(error.getMessage()); }
        }, "vm-shutdown"));
        System.out.println("VectorMatch workbench http://127.0.0.1:" + bound + " | LOCAL_JOURNALED | synthetic market flow");
        app.server.closeFuture().sync();
    }
}
