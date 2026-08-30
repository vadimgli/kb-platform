# Google Cloud Model Armor & Sensitive Data Protection (DLP) Terraform Module

# 1. DLP De-identification Template for PII & Secret Redaction
resource "google_data_loss_prevention_deidentify_template" "pii_redaction" {
  parent       = "projects/${var.project_id}"
  display_name = "artifactforge-pii-redaction-template"
  description  = "Redacts Email, Phone, SSN, Credit Cards, API Tokens, and GCP/AWS Credentials from agent prompts"

  deidentify_config {
    info_type_transformations {
      transformations {
        info_types { name = "EMAIL_ADDRESS" }
        info_types { name = "PHONE_NUMBER" }
        info_types { name = "US_SOCIAL_SECURITY_NUMBER" }
        info_types { name = "CREDIT_CARD_NUMBER" }
        info_types { name = "AUTH_TOKEN" }
        info_types { name = "AWS_CREDENTIALS" }
        info_types { name = "GCP_CREDENTIALS" }
        info_types { name = "IP_ADDRESS" }

        primitive_transformation {
          replace_with_info_type_config = true
        }
      }
    }
  }
}

# 2. DLP Inspection Template
resource "google_data_loss_prevention_inspect_template" "pii_inspection" {
  parent       = "projects/${var.project_id}"
  display_name = "artifactforge-pii-inspect-template"
  description  = "Inspects inbound prompts for sensitive PII, credential tokens, and IP address data types"

  inspect_config {
    info_types { name = "EMAIL_ADDRESS" }
    info_types { name = "PHONE_NUMBER" }
    info_types { name = "US_SOCIAL_SECURITY_NUMBER" }
    info_types { name = "CREDIT_CARD_NUMBER" }
    info_types { name = "AUTH_TOKEN" }
    info_types { name = "AWS_CREDENTIALS" }
    info_types { name = "GCP_CREDENTIALS" }
    info_types { name = "IP_ADDRESS" }

    min_likelihood = "LIKELY"
  }
}
