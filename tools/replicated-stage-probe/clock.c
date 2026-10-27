#define _GNU_SOURCE
#include <jni.h>
#include <time.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

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

JNIEXPORT jlong JNICALL Java_io_vectormatch_cluster_StageTrace_allocateRecording(JNIEnv *env, jclass cls, jstring path, jlong length) {
    (void) cls;
    const char *name = (*env)->GetStringUTFChars(env, path, NULL);
    if (name == NULL) return 0;
    int fd = open(name, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    int problem = fd < 0 ? errno : 0;
    (*env)->ReleaseStringUTFChars(env, path, name);
    struct stat before, after;
    if (!problem && fstat(fd, &before) != 0) problem = errno;
    if (!problem && (!S_ISREG(before.st_mode) || before.st_size != length || length <= 0 || length > 536870912LL)) problem = EINVAL;
    /* Linux fallocate has no glibc posix_fallocate zero-writing fallback. Fail if unsupported. */
    if (!problem && fallocate(fd, FALLOC_FL_KEEP_SIZE, 0, length) != 0) problem = errno;
    if (!problem && fstat(fd, &after) != 0) problem = errno;
    if (!problem && (after.st_size != before.st_size || after.st_ino != before.st_ino)) problem = EIO;
    jlong allocated = problem ? 0 : (jlong) after.st_blocks * 512;
    if (fd >= 0 && close(fd) != 0 && !problem) problem = errno;
    if (problem) {
        char message[256];
        snprintf(message, sizeof(message), "Recording allocation failed: %s (%d)", strerror(problem), problem);
        jclass error = (*env)->FindClass(env, "java/lang/IllegalStateException");
        (*env)->ThrowNew(env, error, message);
        return 0;
    }
    return allocated;
}
