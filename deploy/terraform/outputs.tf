output "instance_ip" {
  description = "External IP of the Aletheia instance"
  value       = google_compute_address.aletheia.address
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "gcloud compute ssh aletheia --zone=${var.zone} --project=${var.project_id}"
}
