plugins { application }

dependencies {
    implementation(project(":core"))
    implementation(project(":cluster"))
    implementation("org.postgresql:postgresql:42.7.10")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.4")
}

application {
    mainClass.set("io.vectormatch.projector.ProjectorMain")
    applicationDefaultJvmArgs = listOf("--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED")
}

tasks.withType<Test>().configureEach {
    jvmArgs(application.applicationDefaultJvmArgs)
    // PostgreSQL integration tests are explicitly skipped unless this is supplied.
    environment("VM_TEST_PG_URL", System.getenv("VM_TEST_PG_URL") ?: "")
    // Enabling the real database suite must invalidate a prior skipped test task.
    inputs.property("postgresIntegrationConfigured", !System.getenv("VM_TEST_PG_URL").isNullOrBlank())
}
