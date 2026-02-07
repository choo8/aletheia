terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Enable Compute Engine API
resource "google_project_service" "compute" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

# Static external IP (free when attached to a running instance)
resource "google_compute_address" "aletheia" {
  name       = "aletheia-ip"
  depends_on = [google_project_service.compute]
}

# Firewall: allow SSH only
resource "google_compute_firewall" "allow_ssh" {
  name    = "aletheia-allow-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.ssh_source_ranges
  target_tags   = ["aletheia"]

  depends_on = [google_project_service.compute]
}

# Firewall: deny all other inbound (lower priority than SSH rule)
resource "google_compute_firewall" "deny_inbound" {
  name     = "aletheia-deny-inbound"
  network  = "default"
  priority = 65534

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["aletheia"]

  depends_on = [google_project_service.compute]
}

# Compute instance
resource "google_compute_instance" "aletheia" {
  name         = "aletheia"
  machine_type = var.machine_type
  tags         = ["aletheia"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.disk_size_gb
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.aletheia.address
    }
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  depends_on = [google_project_service.compute]
}
