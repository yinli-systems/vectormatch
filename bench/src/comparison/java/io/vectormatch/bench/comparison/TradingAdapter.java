package io.vectormatch.bench.comparison;

import java.util.function.BiConsumer;
import static io.vectormatch.bench.comparison.CommonFlow.*;

public interface TradingAdapter extends AutoCloseable {
    void submit(int index, Command command, BiConsumer<Integer,Outcome> completion);
    State state();
    String configuration();
    @Override void close();
}
