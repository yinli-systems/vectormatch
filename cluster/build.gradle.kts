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

tasks.register<JavaExec>("capacityAeronV4") {
    group = "verification"
    description = "Runs one finite 20-second V4 UDP point with physical-order replay and three-node cold restore."
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("io.vectormatch.cluster.RetentionCapacityAeronV4")
    jvmArgs(application.applicationDefaultJvmArgs)
    maxHeapSize = "768m"
    doFirst {
        args(providers.gradleProperty("capacityV4Root").orNull
            ?: throw GradleException("Pass -PcapacityV4Root=<new-state-directory>."),
            providers.gradleProperty("capacityV4Rate").orNull
            ?: throw GradleException("Pass -PcapacityV4Rate=500|1000|2000|4000|6000|7000|8000."),
            providers.gradleProperty("capacityV4Policy").orNull
            ?: throw GradleException("Pass -PcapacityV4Policy=PAUSE|CONTINUE."))
    }
}


val soakAgentSources = sourceSets.create("soakAgent") {
    java.srcDir(rootProject.file("tools/soak-agent"))
}
tasks.register<Jar>("soakAgentJar") {
    dependsOn(tasks.named(soakAgentSources.classesTaskName))
    archiveBaseName.set("vectormatch-soak-agent")
    from(soakAgentSources.output)
    manifest { attributes("Premain-Class" to "io.vectormatch.soak.SoakAgent") }
}
