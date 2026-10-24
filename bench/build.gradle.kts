import java.util.zip.ZipFile

plugins { application }
dependencies {
    implementation(project(":core"))
    implementation("org.hdrhistogram:HdrHistogram:2.2.2")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.4")
}
application { mainClass.set("io.vectormatch.bench.CoreBenchmark") }

// This source set has only the core and JMH dependencies; the legacy application
// and HTTP workload retain their existing runtime classpaths.
val coreJmh = sourceSets.create("jmh")
dependencies {
    add(coreJmh.implementationConfigurationName, project(":core"))
    add(coreJmh.implementationConfigurationName, "org.openjdk.jmh:jmh-core:1.37")
    add(coreJmh.annotationProcessorConfigurationName, "org.openjdk.jmh:jmh-generator-annprocess:1.37")
    testImplementation(coreJmh.output)
}

val jmhJar = tasks.register<Jar>("jmhJar") {
    group = "build"
    description = "Package generated JMH harness classes and discovery resources."
    archiveBaseName.set("vectormatch-core-jmh")
    from(coreJmh.output)
    duplicatesStrategy = DuplicatesStrategy.FAIL
    doLast {
        ZipFile(archiveFile.get().asFile).use { jar ->
            for (name in listOf("META-INF/BenchmarkList", "META-INF/CompilerHints")) {
                val entry = jar.getEntry(name)
                require(entry != null && jar.getInputStream(entry).use { it.readBytes().isNotEmpty() }) {
                    "Missing or empty generated JMH resource: $name"
                }
            }
            require(jar.entries().asSequence().any { it.name.contains("/jmh_generated/") && it.name.endsWith(".class") }) {
                "Missing annotation-processor generated JMH classes"
            }
        }
    }
}

tasks.register<Sync>("jmhInstallDist") {
    group = "distribution"
    description = "Install a CPU-portable lib directory for java -cp 'lib/*' org.openjdk.jmh.Main."
    into(layout.buildDirectory.dir("install/core-jmh"))
    into("lib") {
        from(jmhJar)
        from(configurations[coreJmh.runtimeClasspathConfigurationName])
    }
    duplicatesStrategy = DuplicatesStrategy.FAIL
}

tasks.register<JavaExec>("jmh") {
    group = "verification"
    description = "Run explicit JMH core workloads; defaults are the full finite-batch/cache matrix, not end-to-end latency."
    dependsOn(tasks.named("jmhInstallDist"))
    javaLauncher.set(javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(21)) })
    classpath = files(fileTree(layout.buildDirectory.dir("install/core-jmh/lib")) { include("*.jar") })
    mainClass.set("org.openjdk.jmh.Main")
    workingDir = rootProject.projectDir
    doFirst {
        require(listOf("-rff", "-rf", "-foe").all { flag -> args.count { it == flag } <= 1 }) { "Duplicate JMH result/failure options" }
        if ("-foe" !in args) args("-foe", "true")
        val failure = args.indexOf("-foe")
        require(failure + 1 < args.size && args[failure + 1] == "true") { "JMH must fail on fixture/benchmark errors" }
        if ("-rf" !in args) args("-rf", "json")
        val format = args.indexOf("-rf")
        require(format + 1 < args.size && args[format + 1] == "json") { "Structured JMH JSON output is required" }
        if ("-rff" !in args) args("-rff", layout.buildDirectory.file("reports/jmh/run-${System.currentTimeMillis()}.json").get().asFile.absolutePath)
        val output = args.indexOf("-rff")
        require(output + 1 < args.size) { "JMH -rff requires an output path" }
        val target = rootProject.file(args[output + 1])
        require(!target.exists()) { "Refusing to overwrite existing JMH evidence: $target" }
        target.parentFile.mkdirs()
    }
}

tasks.register<JavaExec>("httpLoad") {
    group = "verification"
    description = "Bounded fixed-arrival HTTP workload against the local workbench (not replicated cluster performance)."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("io.vectormatch.bench.HttpLoadGenerator")
    workingDir = rootProject.projectDir
}

