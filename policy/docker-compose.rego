package shma.docker_compose

deny[msg] {
  some name
  service := input.services[name]
  image := object.get(service, "image", "")
  not contains(image, "@sha256:")
  msg := sprintf("service %q image %q must include @sha256 digest", [name, image])
}

deny[msg] {
  some name
  service := input.services[name]
  ports := object.get(service, "ports", null)
  ports != null
  not object.get(service, "x-shma-service-ports", false)
  msg := sprintf(
    "service %q defines ports but lacks x-shma-service-ports annotation",
    [name],
  )
}

deny[msg] {
  some name
  service := input.services[name]
  user := object.get(service, "user", "")
  user != "65532:65532"
  msg := sprintf("service %q must run as user 65532:65532", [name])
}

deny[msg] {
  some name
  service := input.services[name]
  read_only := object.get(service, "read_only", null)
  read_only != true
  msg := sprintf("service %q must set read_only: true", [name])
}

deny[msg] {
  some name
  service := input.services[name]
  caps := object.get(service, "cap_drop", [])
  count(caps) == 0
  msg := sprintf("service %q must define cap_drop", [name])
}

deny[msg] {
  some name
  service := input.services[name]
  caps := object.get(service, "cap_drop", [])
  count(caps) > 0
  not list_contains_string(caps, "ALL")
  msg := sprintf("service %q cap_drop must include ALL", [name])
}

deny[msg] {
  some name
  service := input.services[name]
  security := object.get(service, "security_opt", [])
  count(security) == 0
  msg := sprintf("service %q must define security_opt", [name])
}

deny[msg] {
  some name
  service := input.services[name]
  security := object.get(service, "security_opt", [])
  not list_contains_string(security, "no-new-privileges:true")
  msg := sprintf(
    "service %q security_opt must include no-new-privileges:true",
    [name],
  )
}

deny[msg] {
  some name
  service := input.services[name]
  security := object.get(service, "security_opt", [])
  not apparmor_defined(security)
  msg := sprintf(
    "service %q security_opt must include an apparmor profile",
    [name],
  )
}

list_contains_string(list, value) {
  list[_] == value
}

apparmor_defined(options) {
  option := options[_]
  startswith(option, "apparmor=")
}
