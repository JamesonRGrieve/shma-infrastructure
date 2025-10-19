# Filter Plugin Reference

This repository exposes a handful of Ansible filter plugins that keep edge automation and package resolution DRY. The sections below summarize the helpers added for the OPNsense roles and platform-aware package maps.

## `platform_map`

`platform_map` reads a distribution-specific mapping and gracefully falls back to operating system family or alias keys. The filter accepts the mapping as the value being filtered and then the following arguments:

1. `distribution` – the `ansible_distribution` fact.
2. `family` – optional `ansible_os_family` fallback.
3. `fallback` – optional alias (for example `AlmaLinux` when mapping older CentOS nodes).
4. `default` – value returned when no keys match.

```yaml
# roles/system_hardening/tasks/packages.yml
- name: Resolve package set for distribution
  ansible.builtin.set_fact:
    hardening_package_target: "{{ hardening_packages_common | platform_map(ansible_distribution, ansible_os_family, default=[]) }}"
```

## `opnsense_caddy_configuration`

Builds the Caddy API payload for the edge firewall based on the exported ingress backends. The filter deduplicates listener addresses, validates backend metadata, and produces the nested structure expected by OPNsense.

```yaml
- name: Build Caddy configuration payload
  ansible.builtin.set_fact:
    opnsense_caddy_configuration: "{{ edge_ingress_backends | default([]) | opnsense_caddy_configuration(bind_definitions) }}"
```

## `opnsense_nginx_payloads`

Generates both upstream and server payloads for the OPNsense Nginx API. It shares the validation logic with the Caddy helper and normalises listener bindings so future backends only have to provide their exports and metadata.

```yaml
- name: Build OPNsense Nginx payloads
  ansible.builtin.set_fact:
    opnsense_nginx_payload: "{{ edge_ingress_backends | default([]) | opnsense_nginx_payloads(bind_definitions, opnsense_nginx_tls_certificate_id) }}"
```

Using these helpers keeps the edge roles and distribution conditionals centralised, reducing opportunities for configuration drift.
