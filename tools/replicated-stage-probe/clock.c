#include <jni.h>
#include <time.h>

/* All JVMs must attest the same Linux boot and time namespace. No wall-clock conversion. */
JNIEXPORT jlong JNICALL Java_io_vectormatch_cluster_StageTrace_monotonicNanos(JNIEnv *env, jclass cls) {
    (void) cls;
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) {
        jclass error = (*env)->FindClass(env, "java/lang/IllegalStateException");
        (*env)->ThrowNew(env, error, "clock_gettime(CLOCK_MONOTONIC) failed");
        return 0;
    }
    return (jlong) value.tv_sec * 1000000000LL + value.tv_nsec;
}
