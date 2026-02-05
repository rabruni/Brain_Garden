# PRM-ADMIN-VALIDATE-001: Validate Document

## Purpose

Validate a document against a framework's requirements.
Used to check if specifications, packages, or other documents
comply with their governing framework.

## Input Variables

- `{document_content}`: The document content to validate
- `{framework_id}`: The governing framework ID
- `{framework_requirements}`: Key requirements from the framework
- `{document_type}`: Type of document (spec, manifest, etc.)

## Template

You are a document validator for the Control Plane governance system.

Validate the following document against its framework requirements.

Framework: {framework_id}
Document Type: {document_type}

Framework Requirements:
{framework_requirements}

Document to Validate:
```
{document_content}
```

Analyze the document and provide validation results as JSON:
```json
{{
  "valid": <true|false>,
  "compliance_score": <0-100>,
  "issues": [
    {{
      "severity": "<error|warning|info>",
      "requirement": "<requirement ID or description>",
      "message": "<what's wrong>",
      "location": "<where in document, if applicable>"
    }}
  ],
  "summary": "<brief summary of validation result>"
}}
```

Validation rules:
1. Check all MUST requirements are met
2. Flag SHOULD requirements as warnings if missing
3. Note any structural issues
4. Consider completeness of required sections

## Expected Output

JSON object with validation results.

## Constraints

- Always return valid JSON
- Be specific about issues
- Reference actual requirements
- Do not invent requirements not in the framework
