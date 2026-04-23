-- =============================================================================
-- Corral transition table — staging surface for Ken's XLSX-unique columns
-- =============================================================================
-- Status: DRAFT. Not executed. Reviewers: TRPA dev team + Ken + Dan.
--
-- Purpose
--   Hold the 8 columns from `2025 Transactions and Allocations Details.xlsx`
--   that Corral does not source today, keyed to `dbo.TdrTransaction` via
--   `TdrTransactionID`. Designed as a **single flat staging table** so it is
--   easy to load, audit, and diff. When the full ERD in
--   `erd/target_schema.md` is ready, this table splits cleanly:
--
--     * AllocationNumber, TransactionCreatedDate, TransactionAcknowledgedDate
--         -> extend `dbo.ResidentialAllocation` with three new columns.
--     * YearBuilt, PmYearBuilt, DetailedDevelopmentType, SupplementalNotes
--         -> `PermitCompletion` sidecar (see target_schema.md).
--     * TrpaMouProjectNumber
--         -> `CrossSystemID` rows with IDType='trpa_mou'.
--
--   SourceFile / SourceRowNumber / LinkageStatus / LoadedAt / IDENTITY key
--   all drop at that point — they only exist to make the staging load
--   auditable.
--
-- What this table does NOT hold
--   * The 12 XLSX columns Corral already sources (Transaction Type, APN,
--     Jurisdiction, Development Right, Quantity, dates, etc.). Those stay
--     in Corral as-is.
--   * `Status Jan 2026` — intentionally dropped. See xlsx_decomposition.md.
--
-- Load cadence
--   On-demand refresh from `notebooks/02_build_transition_table.ipynb`.
--   Idempotent: `UX_CorralTransitionTable_SourceRow` prevents duplicate loads
--   of the same (file, row).
-- =============================================================================

CREATE TABLE dbo.CorralTransitionTable (
    CorralTransitionTableID     int           IDENTITY(1,1) NOT NULL,

    -- FK handle back to Corral. NULL when the XLSX row has no TransactionID
    -- or the parsed ID doesn't resolve (see LinkageStatus='orphan' / 'ambiguous').
    TdrTransactionID            int           NULL,

    -- The XLSX-side synthetic key, e.g. 'EDCCA-ALLOC-1825'. Kept for traceability.
    SyntheticTransactionID      varchar(50)   NULL,

    -- Ken's unique contribution (8 columns):
    AllocationNumber            varchar(30)   NULL,    -- e.g. 'EL-21-O-08'
    TransactionCreatedDate      date          NULL,
    TransactionAcknowledgedDate date          NULL,
    DevelopmentType             varchar(100)  NULL,    -- 'Allocation', 'Banked Unit', etc.
    DetailedDevelopmentType     varchar(500)  NULL,    -- free text
    TrpaMouProjectNumber        varchar(200)  NULL,    -- multi-value possible; parse later
    YearBuilt                   int           NULL,    -- county assessor
    PmYearBuilt                 int           NULL,    -- Ken's internal tracker
    SupplementalNotes           nvarchar(max) NULL,    -- XLSX 'Notes' column

    -- Bookkeeping (all NOT NULL; dropped when schema folds into target ERD):
    LinkageStatus               varchar(30)   NOT NULL,    -- matched | orphan | ambiguous
    SourceFile                  varchar(200)  NOT NULL,    -- e.g. '2025 Transactions and Allocations Details.xlsx'
    SourceRowNumber             int           NOT NULL,    -- 0-based row index within source
    LoadedAt                    datetime2(3)  NOT NULL
        CONSTRAINT DF_CorralTransitionTable_LoadedAt DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_CorralTransitionTable
        PRIMARY KEY CLUSTERED (CorralTransitionTableID),

    CONSTRAINT CK_CorralTransitionTable_LinkageStatus
        CHECK (LinkageStatus IN ('matched', 'orphan', 'ambiguous')),

    CONSTRAINT FK_CorralTransitionTable_TdrTransaction
        FOREIGN KEY (TdrTransactionID)
        REFERENCES dbo.TdrTransaction (TdrTransactionID)
);

-- Lookup by FK — hot path for joining back to dbo.TdrTransaction.
CREATE INDEX IX_CorralTransitionTable_TdrTransactionID
    ON dbo.CorralTransitionTable (TdrTransactionID);

-- Idempotency on reloads. (SourceFile, SourceRowNumber) uniquely identifies
-- a row within any given XLSX snapshot.
CREATE UNIQUE INDEX UX_CorralTransitionTable_SourceRow
    ON dbo.CorralTransitionTable (SourceFile, SourceRowNumber);
