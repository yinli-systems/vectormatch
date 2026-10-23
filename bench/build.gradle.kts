plugins { application }
dependencies {
    implementation(project(":core"))
    implementation("org.hdrhistogram:HdrHistogram:2.2.2")
}
application { mainClass.set("io.vectormatch.bench.CoreBenchmark") }

