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
  msg := "service_container.features requires needs_container_runtime to be true"
}

# Secrets require a namespace to ensure scoped K8s resources.
deny[msg] {
  input.secrets
  (count(input.secrets.env) > 0 or count(input.secrets.files) > 0)
  not input.service_namespace
  msg := "service_namespace must be defined when secrets are present"
}
