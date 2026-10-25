plugins { application; `java-library` }
dependencies {
    api(project(":core"))
    api("io.aeron:aeron-all:1.53.3")
    api("org.agrona:agrona:2.6.1")
}
application {
    mainClass.set("io.vectormatch.cluster.ClusterNodeMain")
    applicationDefaultJvmArgs = listOf("--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED")
}

tasks.register<JavaExec>("failoverSmoke") {
    group = "verification"
    description = "Runs three local JVM nodes, kills the leader, snapshots, and restarts all nodes."
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("io.vectormatch.cluster.ClusterFailoverSmoke")
    jvmArgs(application.applicationDefaultJvmArgs)
}

tasks.withType<Test>().configureEach {
    jvmArgs(application.applicationDefaultJvmArgs)
}

tasks.register<JavaExec>("replicatedBenchmark") {
    group = "verification"
    description = "Measures a short single-inflight closed-loop workload against three real local sync-level-2 processes."
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("io.vectormatch.cluster.ReplicatedBenchmarkSmoke")
    jvmArgs(application.applicationDefaultJvmArgs)
}

tasks.register<JavaExec>("replicatedConcurrencyComparison") {
    group = "verification"
    description = "Runs fair paired 1-client and 4-client sync-level-2 closed-loop replication experiments."
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("io.vectormatch.cluster.ReplicatedConcurrencyComparison")
    jvmArgs(application.applicationDefaultJvmArgs)
}

tasks.register<JavaExec>("asyncMaintenanceSmokeV4") {
    group = "verification"
    description = "Runs a fresh three-JVM UDP asynchronous-maintenance correctness and cold-restore experiment. No capacity claim."
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("io.vectormatch.cluster.RetentionAsyncAeronSmokeV4")
    jvmArgs(application.applicationDefaultJvmArgs)
    maxHeapSize = "256m"
    doFirst {
        args(providers.gradleProperty("asyncV4Root").orNull
            ?: throw GradleException("Pass -PasyncV4Root=<new-state-directory>; existing state is refused."))
    }
}

