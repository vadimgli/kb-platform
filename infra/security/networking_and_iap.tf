# Google Cloud Armor & Identity-Aware Proxy (IAP) Terraform Architecture

# 1. Cloud Armor Security Policy with Rate Limiting & OWASP WAF
resource "google_compute_security_policy" "cloud_armor_policy" {
  name        = "artifactforge-cloud-armor-policy"
  project     = var.project_id
  description = "Enterprise Cloud Armor security policy with rate limiting and OWASP WAF rules"

  # Rule 1: Rate Limiting to prevent LLM abuse / DoS (Max 120 req/min per IP)
  rule {
    action   = "rate_based_ban"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 120
        interval_sec = 60
      }
      ban_threshold {
        count        = 240
        interval_sec = 60
      }
      ban_duration_sec = 300
    }
    description = "Rate limit traffic to max 120 requests per minute per IP"
  }

  # Rule 2: OWASP SQL Injection Protection
  rule {
    action   = "deny(403)"
    priority = "2000"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "Deny SQL Injection attack attempts"
  }

  # Rule 3: OWASP Cross-Site Scripting (XSS) Protection
  rule {
    action   = "deny(403)"
    priority = "2001"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "Deny Cross-Site Scripting (XSS) attempts"
  }

  # Rule 4: OWASP Remote Code Execution (RCE) / Command Injection Protection
  rule {
    action   = "deny(403)"
    priority = "2002"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "Deny Remote Code Execution / Command Injection attempts"
  }

  # Rule 5: Default Allow
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow rule for legitimate traffic"
  }
}

# 2. Serverless Network Endpoint Group (NEG) for Cloud Run
resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  name                  = "artifactforge-cloud-run-neg"
  project               = var.project_id
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_service.artifactforge_api.name
  }
}

# 3. IAP-Enabled Backend Service with Cloud Armor Policy Attached
resource "google_compute_backend_service" "iap_backend_service" {
  name                  = "artifactforge-iap-backend"
  project               = var.project_id
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.cloud_armor_policy.id

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }

  iap {
    oauth2_client_id     = var.iap_oauth_client_id
    oauth2_client_secret = var.iap_oauth_client_secret
  }
}

# 4. Identity-Aware Proxy (IAP) Access for All Internal Domain Users
resource "google_iap_web_backend_service_iam_member" "internal_users_access" {
  project             = var.project_id
  web_backend_service = google_compute_backend_service.iap_backend_service.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = "domain:${var.internal_user_domain}"
}
