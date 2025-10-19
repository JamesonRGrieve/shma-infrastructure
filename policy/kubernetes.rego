package shma.kubernetes

resources[resource] {
  type_name(input) == "array"
  resource := input[_]
}

resources[resource] {
  type_name(input) != "array"
  resource := input
}

all_containers(resource)[container] {
  resource.kind == "Deployment"
  template := object.get(resource.spec, "template", {})
  spec := object.get(template, "spec", {})
  containers := object.get(spec, "containers", [])
  container := containers[_]
}

all_containers(resource)[container] {
  resource.kind == "Deployment"
  template := object.get(resource.spec, "template", {})
  spec := object.get(template, "spec", {})
  init_containers := object.get(spec, "initContainers", [])
  container := init_containers[_]
}

image_has_digest(image) {
  contains(image, "@sha256:")
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

deny[msg] {
  deployment := resources[_]
  deployment.kind == "Deployment"
  container := all_containers(deployment)[_]
  image := container.image
  image != null
  not image_has_digest(image)
  namespace := object.get(deployment.metadata, "namespace", "default")
  name := object.get(deployment.metadata, "name", "<unnamed>")
  container_name := object.get(container, "name", "<unnamed>")
  msg := sprintf(
    "Deployment %s/%s container %s image %q must include an @sha256 digest",
    [namespace, name, container_name, image],
  )
}

deny[msg] {
  deployment := resources[_]
  deployment.kind == "Deployment"
  namespace := object.get(deployment.metadata, "namespace", "default")
  template := object.get(deployment.spec, "template", {})
  template_spec := object.get(template, "spec", {})
  volumes := object.get(template_spec, "volumes", [])
  volume := volumes[_]
  host_path := volume.hostPath
  host_path != null
  pvc := resources[_]
  pvc.kind == "PersistentVolumeClaim"
  object.get(pvc.metadata, "namespace", namespace) == namespace
  object.get(pvc.metadata, "name", "") == object.get(volume, "name", "")
  deployment_name := object.get(deployment.metadata, "name", "<unnamed>")
  volume_name := object.get(volume, "name", "<unnamed>")
  msg := sprintf(
    "Deployment %s/%s volume %s cannot use a hostPath alongside a PersistentVolumeClaim",
    [namespace, deployment_name, volume_name],
  )
}
