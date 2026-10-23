plugins { application }
dependencies {
    implementation(project(":core"))
    implementation("org.hdrhistogram:HdrHistogram:2.2.2")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.4")
}
application { mainClass.set("io.vectormatch.bench.CoreBenchmark") }

tasks.register<JavaExec>("httpLoad") {
    group = "verification"
    description = "Bounded fixed-arrival HTTP workload against the local workbench (not replicated cluster performance)."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("io.vectormatch.bench.HttpLoadGenerator")
    workingDir = rootProject.projectDir
}

