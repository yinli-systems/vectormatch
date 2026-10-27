package io.vectormatch.bench.comparison;

import java.util.*;
import static io.vectormatch.bench.comparison.CommonFlow.*;

/** Independent offline oracle: scans a flat live-order list; no engine or tree-book calls. */
public final class FlatBook {
    private static final class Order {
        final Command command; long remaining;
        Order(Command c) { command=c; remaining=c.quantity(); }
        Resting view() { return new Resting(command.id(),command.account(),command.buy(),command.price(),remaining); }
    }
    private final ArrayList<Order> live = new ArrayList<>();
    private final HashSet<Long> used = new HashSet<>();
    private final long[] base = new long[ACCOUNTS+1], quote = new long[ACCOUNTS+1];
    public FlatBook() { Arrays.fill(base,BASE); Arrays.fill(quote,QUOTE); }
    public int size() { return live.size(); }
    public Resting pick(int index) { return live.get(index).view(); }
    public Outcome apply(Command c) {
        if (c.kind()==Kind.CANCEL) {
            for (int i=0;i<live.size();i++) {
                var o=live.get(i);
                if(o.command.id()==c.id() && o.command.account()==c.account()) {
                    live.remove(i); return new Outcome(true,o.remaining,List.of());
                }
            }
            return new Outcome(false,0,List.of());
        }
        require(used.add(c.id()),"duplicate source order ID");
        long reserved=0;
        for(var o:live) if(o.command.account()==c.account() && o.command.buy()==c.buy())
            reserved=Math.addExact(reserved,c.buy()?Math.multiplyExact(o.command.price(),o.remaining):o.remaining);
        long needed=c.buy()?Math.multiplyExact(c.price(),c.quantity()):c.quantity();
        require((c.buy()?quote[c.account()]:base[c.account()])-reserved>=needed,"oracle funding exhausted");
        long remaining=c.quantity(); var fills=new ArrayList<Fill>();
        while(remaining>0) {
            int best=-1;
            for(int i=0;i<live.size();i++) {
                var o=live.get(i);var m=o.command;
                if(m.buy()==c.buy() || (c.buy()?m.price()>c.price():m.price()<c.price()))continue;
                if(best<0)best=i;
                else {
                    var b=live.get(best).command;
                    if((c.buy()?m.price()<b.price():m.price()>b.price()) || m.price()==b.price()&&m.id()<b.id())best=i;
                }
            }
            if(best<0)break;
            var maker=live.get(best); var m=maker.command;
            require(m.account()!=c.account(),"source requires distinct maker/taker accounts");
            long quantity=Math.min(remaining,maker.remaining),notional=Math.multiplyExact(quantity,m.price());
            int buyer=c.buy()?c.account():m.account(),seller=c.buy()?m.account():c.account();
            base[buyer]=Math.addExact(base[buyer],quantity);base[seller]=Math.subtractExact(base[seller],quantity);
            quote[buyer]=Math.subtractExact(quote[buyer],notional);quote[seller]=Math.addExact(quote[seller],notional);
            fills.add(new Fill(m.id(),c.id(),m.price(),quantity)); remaining-=quantity;maker.remaining-=quantity;
            if(maker.remaining==0)live.remove(best);
        }
        if(remaining>0 && c.kind()==Kind.GTC) { var o=new Order(c);o.remaining=remaining;live.add(o); }
        return new Outcome(true,remaining,fills);
    }
    public State state() {
        long[] br=new long[ACCOUNTS+1],qr=new long[ACCOUNTS+1];
        var orders=new ArrayList<Resting>();
        for(var o:live) {
            orders.add(o.view());int a=o.command.account();
            if(o.command.buy())qr[a]=Math.addExact(qr[a],Math.multiplyExact(o.remaining,o.command.price()));
            else br[a]=Math.addExact(br[a],o.remaining);
        }
        orders.sort(Comparator.comparingLong(Resting::id));var funds=new ArrayList<Funds>();long tb=0,tq=0;
        for(int a=1;a<=ACCOUNTS;a++) {
            require(base[a]>=br[a]&&quote[a]>=qr[a],"negative available assets");
            funds.add(new Funds(a,base[a]-br[a],br[a],quote[a]-qr[a],qr[a]));tb+=base[a];tq+=quote[a];
        }
        require(tb==ACCOUNTS*BASE&&tq==ACCOUNTS*QUOTE,"oracle asset totals changed");
        return new State(funds,orders);
    }
}
