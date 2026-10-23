plugins { application }
dependencies {
    implementation(project(":core"))
    implementation("io.aeron:aeron-all:1.53.3")
    implementation("org.agrona:agrona:2.6.1")
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

