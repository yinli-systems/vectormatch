plugins { application }
dependencies {
    implementation(project(":core"))
    implementation(project(":cluster"))
    implementation(project(":projector"))
    implementation("io.netty:netty-all:4.2.19.Final")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.4")
    implementation("org.hdrhistogram:HdrHistogram:2.2.2")
}
application {
    mainClass.set("io.vectormatch.server.WorkbenchServer")
    applicationDefaultJvmArgs = listOf("--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED")
}

