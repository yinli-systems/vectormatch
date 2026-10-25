# Linux procfs port-range regression

CI17 failed 13 of 441 Java tests before those tests could start their cluster: the JDK readString path returned only byte 51 from a zero-size procfs file. The unchanged failure record is preserved. The fix uses a bounded stream read. Five local tests and the direct Linux source probe pass; complete Linux CI remains required before any new capacity test. No latency, production or funded-trading certification.
