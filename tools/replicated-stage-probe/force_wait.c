#define _GNU_SOURCE
#include <jni.h>
#include <stdatomic.h>
#include <pthread.h>
#include <sys/syscall.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <ctype.h>

typedef struct {
    int64_t force_start, force_end, recording, session, position_start, position_end;
    int64_t outer_start, start_after, end_before, outer_end, cpu_start, cpu_end;
    int64_t voluntary_start, voluntary_end, involuntary_start, involuntary_end;
    int64_t minor_start, minor_end, major_start, major_end;
} Force;
typedef struct {
    uint64_t sequence, sequence_after;
    int64_t start, end;
    char state_before, state_after, wchan[80];
} Sample;
typedef struct {
    pid_t tid;
    int stat_fd, wchan_fd;
    char directory[2048];
    size_t force_capacity, sample_capacity;
    Force *forces;
    Sample *samples;
    int64_t interval;
    atomic_size_t force_count;
    size_t sample_count;
    atomic_uint_fast64_t active, dropped_forces;
    uint64_t dropped_samples, read_errors;
    atomic_int stopped, closed;
    pthread_t sampler;
} Recorder;

static int64_t clock_ns(clockid_t clock_id) {
    struct timespec t;
    if (clock_gettime(clock_id, &t) != 0) return -1;
    return (int64_t)t.tv_sec * 1000000000LL + t.tv_nsec;
}
static void fail(JNIEnv *env, const char *message) {
    jclass error=(*env)->FindClass(env,"java/lang/IllegalStateException");
    if (error) (*env)->ThrowNew(env,error,message);
}
static char read_state(Recorder *r) {
    char b[4096];ssize_t n=pread(r->stat_fd,b,sizeof(b)-1,0);
    if (n<=0) {r->read_errors++;return '?';}
    b[n]=0;char *p=strrchr(b,')');
    if (!p || p[1]!=' ' || !p[2]) {r->read_errors++;return '?';}
    return p[2];
}
static void *observe(void *pointer) {
    Recorder *r=pointer;struct timespec sleep_time={.tv_sec=0,.tv_nsec=r->interval};
    while (!atomic_load_explicit(&r->stopped,memory_order_acquire)) {
        uint64_t sequence=atomic_load_explicit(&r->active,memory_order_acquire);
        if (sequence) {
            if (r->sample_count==r->sample_capacity) {r->dropped_samples++;}
            else {
                Sample *s=&r->samples[r->sample_count];s->sequence=sequence;s->start=clock_ns(CLOCK_MONOTONIC);
                s->state_before=read_state(r);
                ssize_t n=pread(r->wchan_fd,s->wchan,sizeof(s->wchan)-1,0);
                if (n<=0) {r->read_errors++;strcpy(s->wchan,"unavailable");}
                else {
                    s->wchan[n]=0;
                    for (ssize_t i=0;i<n;i++) {
                        if (s->wchan[i]=='\n') s->wchan[i]=0;
                        else if (!isalnum((unsigned char)s->wchan[i]) && s->wchan[i]!='_' && s->wchan[i]!='.') {s->wchan[i]='?';r->read_errors++;}
                    }
                }
                s->state_after=read_state(r);s->end=clock_ns(CLOCK_MONOTONIC);
                s->sequence_after=atomic_load_explicit(&r->active,memory_order_acquire);r->sample_count++;
            }
        }
        nanosleep(&sleep_time,NULL);
    }
    return NULL;
}
JNIEXPORT jlong JNICALL Java_io_vectormatch_cluster_ForceWaitTrace_open(JNIEnv *env,jclass cls,jstring directory,jint fc,jint sc,jlong interval) {
    (void)cls;
    if(fc<1 || fc>250000 || sc<1 || sc>2000000 || interval<250000 || interval>10000000) {fail(env,"Invalid bounded force recorder configuration");return 0;}
    const char *path=(*env)->GetStringUTFChars(env,directory,NULL);if(!path)return 0;
    if(strlen(path)>=2048) {(*env)->ReleaseStringUTFChars(env,directory,path);fail(env,"Evidence path too long");return 0;}
    Recorder *r=calloc(1,sizeof(*r));
    if(!r) {(*env)->ReleaseStringUTFChars(env,directory,path);fail(env,"Recorder allocation failed");return 0;}
    strcpy(r->directory,path);(*env)->ReleaseStringUTFChars(env,directory,path);
    r->tid=(pid_t)syscall(SYS_gettid);r->force_capacity=(size_t)fc;r->sample_capacity=(size_t)sc;r->interval=interval;
    r->forces=calloc((size_t)fc,sizeof(Force));r->samples=calloc((size_t)sc,sizeof(Sample));
    if(!r->forces || !r->samples) {free(r->forces);free(r->samples);free(r);fail(env,"Bounded force tape allocation failed");return 0;}
    char task[128];snprintf(task,sizeof(task),"/proc/self/task/%d/stat",r->tid);r->stat_fd=open(task,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    snprintf(task,sizeof(task),"/proc/self/task/%d/wchan",r->tid);r->wchan_fd=open(task,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(r->stat_fd<0 || r->wchan_fd<0) {
        if(r->stat_fd>=0)close(r->stat_fd);
        if(r->wchan_fd>=0)close(r->wchan_fd);
        free(r->forces);free(r->samples);free(r);fail(env,"Cannot observe own recorder task");return 0;
    }
    int rc=pthread_create(&r->sampler,NULL,observe,r);
    if(rc) {close(r->stat_fd);close(r->wchan_fd);free(r->forces);free(r->samples);free(r);fail(env,"Sampler creation failed");return 0;}
    printf("VECTOR_FORCE_WAIT_READY tid=%d intervalNs=%lld forceCapacity=%d sampleCapacity=%d\n",r->tid,(long long)interval,fc,sc);fflush(stdout);
    return (jlong)(intptr_t)r;
}
JNIEXPORT void JNICALL Java_io_vectormatch_cluster_ForceWaitTrace_start(JNIEnv *env,jclass cls,jlong handle) {
    (void)cls;Recorder *r=(Recorder*)(intptr_t)handle;
    if(!r || syscall(SYS_gettid)!=r->tid || atomic_load(&r->closed) || atomic_load(&r->active)) {fail(env,"Invalid force recorder ownership/lifecycle");return;}
    size_t n=atomic_load_explicit(&r->force_count,memory_order_relaxed);
    if(n==r->force_capacity) {atomic_fetch_add(&r->dropped_forces,1);return;}
    Force *f=&r->forces[n];struct rusage u;f->outer_start=clock_ns(CLOCK_MONOTONIC);
    if(getrusage(RUSAGE_THREAD,&u)!=0) {fail(env,"Thread resource counters unavailable");return;}
    f->voluntary_start=u.ru_nvcsw;f->involuntary_start=u.ru_nivcsw;f->minor_start=u.ru_minflt;f->major_start=u.ru_majflt;
    f->cpu_start=clock_ns(CLOCK_THREAD_CPUTIME_ID);f->start_after=clock_ns(CLOCK_MONOTONIC);
    if(f->cpu_start<0 || f->outer_start<0 || f->start_after<0) {fail(env,"Force clocks unavailable");return;}
    atomic_store_explicit(&r->active,n+1,memory_order_release);
}
JNIEXPORT void JNICALL Java_io_vectormatch_cluster_ForceWaitTrace_finish(JNIEnv *env,jclass cls,jlong handle,jlong start,jlong end,jlong recording,jlong session,jlong position_start,jlong position_end) {
    (void)cls;Recorder *r=(Recorder*)(intptr_t)handle;
    if(!r || syscall(SYS_gettid)!=r->tid) {fail(env,"Invalid force recorder thread");return;}
    uint64_t sequence=atomic_exchange_explicit(&r->active,0,memory_order_acq_rel);
    if(!sequence) {if(atomic_load(&r->force_count)==r->force_capacity)return;fail(env,"Missing active force");return;}
    Force *f=&r->forces[sequence-1];struct rusage u;f->end_before=clock_ns(CLOCK_MONOTONIC);f->cpu_end=clock_ns(CLOCK_THREAD_CPUTIME_ID);
    if(getrusage(RUSAGE_THREAD,&u)!=0) {fail(env,"Thread resource counters unavailable");return;}
    f->voluntary_end=u.ru_nvcsw;f->involuntary_end=u.ru_nivcsw;f->minor_end=u.ru_minflt;f->major_end=u.ru_majflt;f->outer_end=clock_ns(CLOCK_MONOTONIC);
    f->force_start=start;f->force_end=end;f->recording=recording;f->session=session;f->position_start=position_start;f->position_end=position_end;
    if(f->cpu_end<f->cpu_start || f->outer_start>f->start_after || f->start_after>start || start>end || end>f->end_before || f->end_before>f->outer_end) {fail(env,"Invalid force counter envelope");return;}
    atomic_store_explicit(&r->force_count,(size_t)sequence,memory_order_release);
}
static FILE *output(Recorder *r,const char *suffix) {
    char path[2300];snprintf(path,sizeof(path),"%s/thread-%d-%s",r->directory,r->tid,suffix);
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0)return NULL;
    FILE *f=fdopen(fd,"w");if(!f)close(fd);return f;
}
JNIEXPORT void JNICALL Java_io_vectormatch_cluster_ForceWaitTrace_close(JNIEnv *env,jclass cls,jlong handle) {
    (void)cls;Recorder *r=(Recorder*)(intptr_t)handle;if(!r || atomic_exchange(&r->closed,1))return;
    atomic_store_explicit(&r->stopped,1,memory_order_release);pthread_join(r->sampler,NULL);
    size_t count=atomic_load_explicit(&r->force_count,memory_order_acquire);FILE *out=output(r,"forces.csv");
    if(!out) {fail(env,"Cannot create force evidence");return;}
    fprintf(out,"sequence,tid,recording,session,position_start,position_end,force_start,force_end,outer_start,start_after,end_before,outer_end,cpu_start,cpu_end,voluntary_start,voluntary_end,involuntary_start,involuntary_end,minor_start,minor_end,major_start,major_end\n");
    for(size_t n=0;n<count;n++) {
        Force *f=&r->forces[n];int64_t v[]={f->recording,f->session,f->position_start,f->position_end,f->force_start,f->force_end,f->outer_start,f->start_after,f->end_before,f->outer_end,f->cpu_start,f->cpu_end,f->voluntary_start,f->voluntary_end,f->involuntary_start,f->involuntary_end,f->minor_start,f->minor_end,f->major_start,f->major_end};
        fprintf(out,"%zu,%d",n+1,r->tid);for(size_t i=0;i<sizeof(v)/sizeof(v[0]);i++)fprintf(out,",%lld",(long long)v[i]);fputc('\n',out);
    }
    int bad=ferror(out);bad|=fclose(out)!=0;if(bad) {fail(env,"Force evidence write failed");return;}
    out=output(r,"samples.csv");if(!out) {fail(env,"Cannot create sampling evidence");return;}
    fprintf(out,"sequence,sequence_after,start,end,state_before,state_after,wchan\n");
    for(size_t n=0;n<r->sample_count;n++) {Sample *s=&r->samples[n];fprintf(out,"%llu,%llu,%lld,%lld,%c,%c,%s\n",(unsigned long long)s->sequence,(unsigned long long)s->sequence_after,(long long)s->start,(long long)s->end,s->state_before,s->state_after,s->wchan);}
    bad=ferror(out);bad|=fclose(out)!=0;if(bad) {fail(env,"Sampling evidence write failed");return;}
    out=output(r,"complete.json");if(!out) {fail(env,"Cannot close force evidence");return;}
    fprintf(out,"{\"tid\":%d,\"forces\":%zu,\"samples\":%zu,\"droppedForces\":%llu,\"droppedSamples\":%llu,\"readErrors\":%llu,\"intervalNs\":%lld,\"activeAtClose\":%llu}\n",r->tid,count,r->sample_count,(unsigned long long)atomic_load(&r->dropped_forces),(unsigned long long)r->dropped_samples,(unsigned long long)r->read_errors,(long long)r->interval,(unsigned long long)atomic_load(&r->active));
    bad=ferror(out);bad|=fclose(out)!=0;close(r->stat_fd);close(r->wchan_fd);
    /* Keep bounded arrays until JVM exit: application shutdown hooks may overlap the final append. */
    if(bad)fail(env,"Force completion evidence write failed");
}
