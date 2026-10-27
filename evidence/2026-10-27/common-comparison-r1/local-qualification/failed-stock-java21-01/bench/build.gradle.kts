import java.util.zip.ZipFile

plugins { application }
dependencies {
    implementation(project(":core"))
    implementation(project(":cluster"))
    implementation("org.hdrhistogram:HdrHistogram:2.2.2")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.4")
}
application { mainClass.set("io.vectormatch.bench.CoreBenchmark") }

// An isolated comparison classpath avoids mixing exchange-core's Agrona/Chronicle
// dependencies into the application, Aeron runtime or existing benchmarks.
val comparison = sourceSets.create("comparison")
val comparisonTest = sourceSets.create("comparisonTest")
dependencies {
    add(comparison.implementationConfigurationName, project(":core"))
    add(comparison.implementationConfigurationName, "exchange.core2:exchange-core:0.5.3")
    add(comparison.implementationConfigurationName, "com.fasterxml.jackson.core:jackson-databind:2.22.4")
    add(comparison.runtimeOnlyConfigurationName, "org.slf4j:slf4j-simple:1.7.36")
    add(comparisonTest.implementationConfigurationName, comparison.output)
    add(comparisonTest.implementationConfigurationName, platform("org.junit:junit-bom:5.11.4"))
    add(comparisonTest.implementationConfigurationName, "org.junit.jupiter:junit-jupiter")
    add(comparisonTest.runtimeOnlyConfigurationName, "org.junit.platform:junit-platform-launcher")
}
configurations[comparisonTest.implementationConfigurationName].extendsFrom(configurations[comparison.implementationConfigurationName])
configurations[comparisonTest.runtimeOnlyConfigurationName].extendsFrom(configurations[comparison.runtimeOnlyConfigurationName])
val comparisonTests = tasks.register<Test>("comparisonTest") {
    testClassesDirs = comparisonTest.output.classesDirs
    classpath = comparisonTest.runtimeClasspath
    jvmArgs("--add-opens=java.base/java.lang.reflect=ALL-UNNAMED", "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.nio=ALL-UNNAMED", "--add-exports=java.base/jdk.internal.ref=ALL-UNNAMED",
        "--add-exports=java.base/sun.nio.ch=ALL-UNNAMED")
    maxHeapSize = "1g"
}
tasks.named("check") { dependsOn(comparisonTests) }
val comparisonJar = tasks.register<Jar>("comparisonJar") {
    archiveBaseName.set("vectormatch-common-comparison")
    from(comparison.output)
}
tasks.register<Sync>("comparisonInstallDist") {
    into(layout.buildDirectory.dir("install/common-comparison/lib"))
    from(comparisonJar)
    from(configurations[comparison.runtimeClasspathConfigurationName])
    duplicatesStrategy = DuplicatesStrategy.FAIL
}

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
        val arguments = args?.toMutableList() ?: mutableListOf()
        require(listOf("-rff", "-rf", "-foe").all { flag -> arguments.count { it == flag } <= 1 }) { "Duplicate JMH result/failure options" }
        if ("-foe" !in arguments) arguments.addAll(listOf("-foe", "true"))
        val failure = arguments.indexOf("-foe")
        require(failure + 1 < arguments.size && arguments[failure + 1] == "true") { "JMH must fail on fixture/benchmark errors" }
        if ("-rf" !in arguments) arguments.addAll(listOf("-rf", "json"))
        val format = arguments.indexOf("-rf")
        require(format + 1 < arguments.size && arguments[format + 1] == "json") { "Structured JMH JSON output is required" }
        if ("-rff" !in arguments) arguments.addAll(listOf("-rff", layout.buildDirectory.file("reports/jmh/run-${System.currentTimeMillis()}.json").get().asFile.absolutePath))
        val output = arguments.indexOf("-rff")
        require(output + 1 < arguments.size) { "JMH -rff requires an output path" }
        val target = rootProject.file(arguments[output + 1])
        require(!target.exists()) { "Refusing to overwrite existing JMH evidence: $target" }
        target.parentFile.mkdirs()
        setArgs(arguments)
    }
}

tasks.register<JavaExec>("httpLoad") {
    group = "verification"
    description = "Bounded fixed-arrival HTTP workload against the local workbench (not replicated cluster performance)."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("io.vectormatch.bench.HttpLoadGenerator")
    workingDir = rootProject.projectDir
}

