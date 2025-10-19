package shma.service

deny[msg] {
  image := input.service_image

  not image_digest_pinned(image)
  msg := sprintf("service_image %q must be pinned by immutable digest", [image])
}

image_digest_pinned(image) {
  contains(image, "@sha256:")

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
  (count(secrets_env_entries) > 0 or count(secrets_file_entries) > 0)
  not input.service_namespace
  msg := "service_namespace must be defined when secrets are present"
}

# Enforce basic complexity requirements for inline secret values.
deny[msg] {
  secret := secrets_env_entries[_]
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

secrets_env_entries[secret] {
  items := input.secrets.items
  items != null
  some i
  item := items[i]
  t := lower(item.type)
  t == "env"
  secret := item
}

secrets_env_entries[secret] {
  not input.secrets.items
  some i
  secret := input.secrets.env[i]
}

secrets_env_entries[secret] {
  items := input.secrets.items
  items != null
  some i
  item := items[i]
  not item.type
  secret := item
}

secrets_file_entries[secret] {
  items := input.secrets.items
  items != null
  some i
  item := items[i]
  t := lower(item.type)
  t == "file"
  secret := item
}

secrets_file_entries[secret] {
  not input.secrets.items
  some i
  secret := input.secrets.files[i]
}

secrets_file_entries[secret] {
  items := input.secrets.items
  items != null
  some i
  item := items[i]
  not item.type
  item.target
  secret := item
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

# Prevent implicit port exposure when no service_ports declared.
deny[msg] {
  not service_ports_defined
  services := object.get(input, "services", [])
  service := services[_]
  ports := object.get(service, "ports", [])
  count(ports) > 0
  msg := "services[*].ports requires service_ports to be defined"
}

service_ports_defined {
  ports := object.get(input, "service_ports", [])
  count(ports) > 0
}

# Ensure hostPath style mounts are only used intentionally.
deny[msg] {
  volume := input.service_volumes[_]
  volume.host_path_type
  not volume.host_path
  msg := sprintf("service volume %q sets host_path_type without host_path", [volume.name])
}

deny[msg] {
  volume := input.service_volumes[_]
  path := volume.host_path
  path != null
  not startswith(path, "/")
  msg := sprintf("service volume %q host_path %q must be an absolute path", [volume.name, path])
}
