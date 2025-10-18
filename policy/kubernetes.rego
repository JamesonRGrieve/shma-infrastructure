package shma.kubernetes

resources[resource] {
  type_name(input) == "array"
  resource := input[_]
}

resources[resource] {
  type_name(input) != "array"
  resource := input
}

deprecated_apis := {
  "extensions/v1beta1",
  "apps/v1beta1",
  "apps/v1beta2",
  "networking.k8s.io/v1beta1",
  "policy/v1beta1",
}

deny[msg] {
  resource := resources[_]
  api := resource.apiVersion
  api != null
  api := deprecated_apis[_]
  name := resource.metadata.name
  kind := resource.kind
  msg := sprintf("%s/%s uses deprecated apiVersion %s", [kind, name, api])
}
