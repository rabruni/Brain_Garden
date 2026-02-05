# Requirements

## Functional Requirements

### FR-1: Handler Registry

- FR-1.1: Handlers MUST be registerable via decorator pattern
- FR-1.2: Registry MUST track handler metadata (name, description, category, capability)
- FR-1.3: Registry MUST support listing all handlers
- FR-1.4: Registry MUST support handler invocation by name

### FR-2: Session Management

- FR-2.1: Sessions MUST have unique IDs (SES-CHAT-YYYYMMDD-xxxxxxxx)
- FR-2.2: Sessions MUST track turn count
- FR-2.3: Sessions MUST create ledger on first turn
- FR-2.4: Sessions MUST record file reads as evidence

### FR-3: Query Classification

- FR-3.1: Classifier MUST support regex patterns
- FR-3.2: Classifier MUST support fuzzy matching
- FR-3.3: Classifier MUST extract arguments from queries
- FR-3.4: Classifier MUST handle natural language variations

### FR-4: Browse Operations

- FR-4.1: BROWSE_CODE MUST read any file and return contents
- FR-4.2: BROWSE_DIR MUST list directory contents with sizes
- FR-4.3: SEARCH_CODE MUST grep for patterns in codebase

### FR-5: Package Operations

- FR-5.1: PACKAGE_LIST MUST show installed and available packages
- FR-5.2: PACKAGE_INSPECT MUST show manifest and file list
- FR-5.3: PACKAGE_PREFLIGHT MUST run validation without install
- FR-5.4: PACKAGE_INSTALL MUST install from staging/store
- FR-5.5: PACKAGE_UNINSTALL MUST remove package and update registries
- FR-5.6: PACKAGE_STAGE MUST prepare package for install

### FR-6: Ledger Operations

- FR-6.1: LEDGER_QUERY MUST show recent entries
- FR-6.2: LEDGER_QUERY MUST support filtering by event type
- FR-6.3: LEDGER_QUERY MUST show session ledgers

### FR-7: Help Operations

- FR-7.1: HELP MUST list all available commands
- FR-7.2: HELP MUST group commands by category
- FR-7.3: HELP MUST show capability requirements

## Non-Functional Requirements

### NFR-1: Performance

- NFR-1.1: Query classification MUST complete in <10ms
- NFR-1.2: File reads MUST stream for files >1MB
- NFR-1.3: Directory listings MUST limit to 100 items

### NFR-2: Security

- NFR-2.1: Write operations MUST require admin capability
- NFR-2.2: File reads MUST be confined to Control Plane root
- NFR-2.3: Package operations MUST validate signatures (if enabled)

### NFR-3: Auditability

- NFR-3.1: All turns MUST log to session ledger
- NFR-3.2: All file reads MUST be recorded as evidence
- NFR-3.3: All package operations MUST log to L-PACKAGE ledger

### NFR-4: Extensibility

- NFR-4.1: New handlers MUST be addable without core changes
- NFR-4.2: Classification patterns MUST be configurable
- NFR-4.3: Handler categories MUST be extensible
