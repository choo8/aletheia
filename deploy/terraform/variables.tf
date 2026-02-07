variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "GCE machine type (e2-micro is free tier)"
  type        = string
  default     = "e2-micro"
}

variable "disk_size_gb" {
  description = "Boot disk size in GB (30 GB is free tier limit for pd-standard)"
  type        = number
  default     = 30
}

variable "ssh_source_ranges" {
  description = "CIDR ranges allowed to SSH (default: anywhere, Tailscale recommended)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
