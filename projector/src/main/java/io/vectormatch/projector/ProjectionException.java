package io.vectormatch.projector;

/** Data-integrity faults are terminal: an operator must resolve lineage or restore missing data. */
public sealed class ProjectionException extends IllegalStateException
        permits ProjectionException.Gap, ProjectionException.PayloadConflict {
    private static final long serialVersionUID = 1L;
    protected ProjectionException(String message) { super(message); }

    public static final class Gap extends ProjectionException {
        private static final long serialVersionUID = 1L;
        public Gap(String message) { super(message); }
    }

    public static final class PayloadConflict extends ProjectionException {
        private static final long serialVersionUID = 1L;
        public PayloadConflict(String message) { super(message); }
    }
}
