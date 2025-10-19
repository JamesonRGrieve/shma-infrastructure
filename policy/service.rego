package shma.service

deny[msg] {
  image := input.service_image
  not image_pinned(image)
  msg := sprintf("service_image %q must include a pinned tag or digest", [image])
}

image_pinned(image) {
  contains(image, "@sha256:")
}

image_pinned(image) {
  contains(image, ":")
  not endswith(lower(image), ":latest")
}

# Ensure LXC features are gated behind needs_container_runtime.
deny[msg] {
  input.needs_container_runtime != true
  input.service_container.features
  msg := "service_container.features requires needs_container_runtime=true"
}

# Secrets require a namespace to ensure scoped K8s resources.
deny[msg] {
  input.secrets
  (count(input.secrets.env) > 0 or count(input.secrets.files) > 0)
  not input.service_namespace
  msg := "service_namespace must be defined when secrets are present"
}

# Enforce basic complexity requirements for inline secret values.
deny[msg] {
  secret := input.secrets.env[_]
  value := secret.value
  not secret_complex(value)
  msg := sprintf(
    "secret %q must be at least 16 characters and include multiple character classes",
    [secret.name],
  )
}

secret_complex(value) {
  secret_length_ok(value)
  count(secret_character_classes(value)) >= 2
}

secret_length_ok(value) {
  re_match("^.{16,}$", value)
}

secret_character_classes(value)[class] {
  re_match("[a-z]", value)
  class := "lower"
}

secret_character_classes(value)[class] {
  re_match("[A-Z]", value)
  class := "upper"
}

secret_character_classes(value)[class] {
  re_match("[0-9]", value)
  class := "digit"
}

secret_character_classes(value)[class] {
  re_match("[^A-Za-z0-9]", value)
  class := "special"
}

# Resource requests must stay within supported bounds.
deny[msg] {
  memory := input.service_resources.memory_mb
  not within_range(memory, 64, 65536)
  msg := sprintf("service_resources.memory_mb %d must be between 64 and 65536", [memory])
}

deny[msg] {
  cpu := input.service_resources.cpu_cores
  not within_range(cpu, 0.1, 64)
  msg := sprintf("service_resources.cpu_cores %v must be between 0.1 and 64", [cpu])
}

within_range(value, min, max) {
  value >= min
  value <= max
}

# Disallow privileged host port exposure.
deny[msg] {
  port := input.service_ports[_]
  port.published < 1024
  msg := sprintf("service port %v publishes privileged host port %v", [port.target, port.published])
}

deny[msg] {
  port := input.service_ports[_]
  port.host_ip
  port.host_ip == "0.0.0.0"
  msg := sprintf("service port %v exposes 0.0.0.0; use a specific host_ip", [port.target])
}
