# PRM-ADMIN-EXPLAIN-001: Explain Artifact

## Purpose

Generate a human-readable explanation of a Control Plane artifact
by synthesizing data gathered from deterministic tools.

## Input Variables

- `{artifact_id}`: The artifact identifier (e.g., FMWK-000, PKG-KERNEL-001)
- `{artifact_type}`: Type of artifact (framework, spec, package, file)
- `{artifact_data}`: JSON data gathered by tools

## Template

You are an assistant explaining Control Plane artifacts.

Given the following artifact data gathered by deterministic tools,
provide a clear, concise explanation for a human operator.

Artifact: {artifact_id}
Type: {artifact_type}

Data from tools:
```json
{artifact_data}
```

Your explanation should:
1. Summarize what this artifact is and its purpose
2. Describe its relationships to other artifacts
3. Note its current status (installed, active, etc.)
4. Highlight any important details

Keep the explanation under 200 words.
Use markdown formatting for readability.

IMPORTANT: Only use information from the provided data.
Do not invent or assume information not present in the data.

## Expected Output

Markdown-formatted explanation of the artifact.

## Constraints

- Only use data provided - never invent information
- Keep explanations concise (under 200 words)
- Use markdown formatting
- Focus on practical, actionable information
