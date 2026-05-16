-- =============================================================================
-- Canonical row-level schema for cumulative accounting
-- =============================================================================
-- Designed 2026-05-15. Companion to erd/canonical_row_level_schema.md.
-- This is the DDL for the 8 core entities + the lookup tables they reference.
-- Naming convention: PascalCase, singular nouns. PK is <Entity>ID.
-- FK fields have the same name as the referenced PK.
-- Reserved-word fields ([Group]) are bracket-quoted.
--
-- Target: SQL Server (Enterprise GDB). Adjust types for PostgreSQL/Oracle as
-- needed (NVARCHAR -> VARCHAR; DATETIME2 -> TIMESTAMP).
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- LOOKUPS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE Commodity (
    CommodityCode    VARCHAR(4)   NOT NULL PRIMARY KEY,    -- 'RES' | 'RBU' | 'CFA' | 'TAU'
    Commodity        VARCHAR(50)  NOT NULL,                -- 'Residential allocations', etc.
    Unit             VARCHAR(10)  NOT NULL,                -- 'units' | 'sq ft'
    BasePlanEra      VARCHAR(4)   NOT NULL                 -- '1987' (RES/RBU/TAU) | '2012' (CFA partial)
);

CREATE TABLE Jurisdiction (
    JurisdictionID   INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    JurisdictionCode VARCHAR(4)   NOT NULL UNIQUE,         -- 'PL' | 'SLT' | 'WA' | 'DG' | 'EL' | 'TRPA'
    JurisdictionName VARCHAR(50)  NOT NULL,
    IsTrpaManaged    BIT          NOT NULL DEFAULT 0
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. PARCEL (already exists; included here for FK completeness)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE Parcel (
    ParcelID         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    APN              VARCHAR(15)  NOT NULL UNIQUE,         -- canonical form, e.g. '023-181-038'
    JurisdictionID   INT          NOT NULL,
    -- Geometry would be added here; see TRPA Parcels FeatureServer for spatial
    -- coverage. For the data-only schema we link by APN.
    CreatedAt        DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Parcel_Jurisdiction FOREIGN KEY (JurisdictionID) REFERENCES Jurisdiction(JurisdictionID)
);
CREATE INDEX IX_Parcel_APN ON Parcel(APN);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. DEVELOPMENT RIGHT POOL
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE DevelopmentRightPool (
    PoolID           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    PoolName         VARCHAR(120) NOT NULL UNIQUE,         -- 'Residential Allocation - Placer County'
    CommodityCode    VARCHAR(4)   NOT NULL,
    JurisdictionID   INT          NULL,                    -- nullable for TRPA pools
    PoolType         VARCHAR(30)  NOT NULL,                -- 'Jurisdiction' | 'TRPA Managed' | 'Unreleased Reserve' | 'Bonus Subset'
    PlanEra          VARCHAR(10)  NOT NULL DEFAULT 'Both', -- '1987' | '2012' | 'Both'
    CONSTRAINT FK_Pool_Commodity    FOREIGN KEY (CommodityCode)  REFERENCES Commodity(CommodityCode),
    CONSTRAINT FK_Pool_Jurisdiction FOREIGN KEY (JurisdictionID) REFERENCES Jurisdiction(JurisdictionID)
);
CREATE INDEX IX_Pool_Commodity ON DevelopmentRightPool(CommodityCode);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. ALLOCATION RIGHT (the missing primary entity for non-RES commodities)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE AllocationRight (
    AllocationRightID  INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    AllocationNumber   VARCHAR(40)  NOT NULL,              -- human-readable, e.g. 'RES-CSLT-1247', 'CFA-EL-BLK-0042'
    CommodityCode      VARCHAR(4)   NOT NULL,
    Quantity           INT          NOT NULL DEFAULT 1,    -- 1 for RES/RBU/TAU; sqft block for CFA
    PlanEra            VARCHAR(10)  NOT NULL,              -- '1987' | '2012'
    IssuanceYear       INT          NULL,                  -- when TRPA released the right; null for Unreleased
    CurrentPoolID      INT          NULL,                  -- where it sits now (null if Allocated)
    CurrentParcelID    INT          NULL,                  -- where it sits now (null if InPool/TRPAPool/Unreleased)
    CurrentStatus      VARCHAR(15)  NOT NULL,              -- 'Allocated' | 'InPool' | 'TRPAPool' | 'Unreleased' | 'Banked' | 'Converted' | 'Retired'
    ConstructionStatus VARCHAR(15)  NULL,                  -- 'NotApplicable' | 'NotStarted' | 'InProgress' | 'Completed'; null for non-Allocated
    OriginatingEventID INT          NULL,                  -- FK to first event in lifecycle (set after Event insert)
    IsSynthesized      BIT          NOT NULL DEFAULT 0,    -- true for rows backfilled without a source record (pre-Accela CFA/TAU/1987 RES synthesis)
    CreatedAt          DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt          DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Right_Commodity FOREIGN KEY (CommodityCode)   REFERENCES Commodity(CommodityCode),
    CONSTRAINT FK_Right_Pool      FOREIGN KEY (CurrentPoolID)   REFERENCES DevelopmentRightPool(PoolID),
    CONSTRAINT FK_Right_Parcel    FOREIGN KEY (CurrentParcelID) REFERENCES Parcel(ParcelID),
    CONSTRAINT CK_Right_StatusLocation CHECK (
        -- Status must agree with where the row sits
        (CurrentStatus = 'Allocated'  AND CurrentParcelID IS NOT NULL AND CurrentPoolID IS NULL)  OR
        (CurrentStatus IN ('InPool','TRPAPool','Unreleased') AND CurrentPoolID IS NOT NULL AND CurrentParcelID IS NULL) OR
        (CurrentStatus IN ('Banked','Converted','Retired') AND CurrentParcelID IS NOT NULL)
    )
);
CREATE INDEX IX_Right_CommodityStatus ON AllocationRight(CommodityCode, CurrentStatus);
CREATE INDEX IX_Right_Pool             ON AllocationRight(CurrentPoolID)   WHERE CurrentPoolID   IS NOT NULL;
CREATE INDEX IX_Right_Parcel           ON AllocationRight(CurrentParcelID) WHERE CurrentParcelID IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. ALLOCATION EVENT (the missing temporal entity)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE AllocationEvent (
    AllocationEventID  INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    AllocationRightID  INT          NOT NULL,
    EventType          VARCHAR(25)  NOT NULL,              -- 'Issuance' | 'Release' | 'Assignment' | 'Transfer' | 'Conversion' | 'Bank' | 'Withdraw' | 'ConstructionPermit' | 'ConstructionComplete' | 'Retirement'
    EventDate          DATE         NOT NULL,
    FromStatus         VARCHAR(15)  NULL,                  -- null for first issuance
    FromPoolID         INT          NULL,
    FromParcelID       INT          NULL,
    ToStatus           VARCHAR(15)  NOT NULL,
    ToPoolID           INT          NULL,
    ToParcelID         INT          NULL,
    QuantityAffected   INT          NOT NULL,              -- default = right's Quantity; differs for splits
    ApprovingAgency    VARCHAR(20)  NULL,                  -- 'TRPA' | 'CSLT' | etc.
    TransactionRef     VARCHAR(40)  NULL,                  -- LT Info / Accela transaction number
    Comments           VARCHAR(500) NULL,
    SourceSystemRecord VARCHAR(80)  NULL,                  -- provenance: 'Corral_TdrTransaction_12345' | 'SYNTHESIZED:2026-05-backfill'
    RecordedAt         DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Event_Right        FOREIGN KEY (AllocationRightID) REFERENCES AllocationRight(AllocationRightID),
    CONSTRAINT FK_Event_FromPool     FOREIGN KEY (FromPoolID)        REFERENCES DevelopmentRightPool(PoolID),
    CONSTRAINT FK_Event_FromParcel   FOREIGN KEY (FromParcelID)      REFERENCES Parcel(ParcelID),
    CONSTRAINT FK_Event_ToPool       FOREIGN KEY (ToPoolID)          REFERENCES DevelopmentRightPool(PoolID),
    CONSTRAINT FK_Event_ToParcel     FOREIGN KEY (ToParcelID)        REFERENCES Parcel(ParcelID)
);
CREATE INDEX IX_Event_Right ON AllocationEvent(AllocationRightID, EventDate);
CREATE INDEX IX_Event_Date  ON AllocationEvent(EventDate);
CREATE INDEX IX_Event_Type  ON AllocationEvent(EventType);


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. BANKED DEVELOPMENT RIGHT (replacement for the drift-prone pci.BankedQuantity)
-- ─────────────────────────────────────────────────────────────────────────────
-- This is the table form. In practice it should be a VIEW over AllocationEvent
-- filtered to bank/withdraw events. Defining as a table here for completeness;
-- the view definition is in erd/canonical_views.sql.

CREATE TABLE BankedDevelopmentRight (
    BankedRightID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ParcelID            INT          NOT NULL,
    CommodityCode       VARCHAR(4)   NOT NULL,
    Quantity            INT          NOT NULL,
    BankedDate          DATE         NOT NULL,
    SourceEventID       INT          NOT NULL,              -- AllocationEvent that created the bank
    Status              VARCHAR(15)  NOT NULL DEFAULT 'Active',  -- 'Active' | 'Used' | 'Withdrawn' | 'Expired'
    UsedInEventID       INT          NULL,                  -- AllocationEvent that drew from the bank
    LandCapability      VARCHAR(20)  NULL,
    IPESScore           INT          NULL,
    CONSTRAINT FK_Bank_Parcel    FOREIGN KEY (ParcelID)      REFERENCES Parcel(ParcelID),
    CONSTRAINT FK_Bank_Commodity FOREIGN KEY (CommodityCode) REFERENCES Commodity(CommodityCode),
    CONSTRAINT FK_Bank_Source    FOREIGN KEY (SourceEventID) REFERENCES AllocationEvent(AllocationEventID),
    CONSTRAINT FK_Bank_Used      FOREIGN KEY (UsedInEventID) REFERENCES AllocationEvent(AllocationEventID)
);
CREATE INDEX IX_Bank_ParcelCommodity ON BankedDevelopmentRight(ParcelID, CommodityCode);
CREATE INDEX IX_Bank_Status          ON BankedDevelopmentRight(Status);


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. RESIDENTIAL PROJECT
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE ResidentialProject (
    ProjectID         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ProjectName       VARCHAR(80)  NOT NULL,
    YearCompleted     INT          NOT NULL,
    PrimaryParcelID   INT          NULL,                   -- canonical parcel for the project
    TotalUnits        INT          NOT NULL,
    AffordableUnits   INT          NOT NULL DEFAULT 0,
    ModerateUnits     INT          NOT NULL DEFAULT 0,
    AchievableUnits   INT          NOT NULL DEFAULT 0,
    JurisdictionID    INT          NOT NULL,
    Notes             VARCHAR(500) NULL,
    CONSTRAINT FK_Project_Parcel       FOREIGN KEY (PrimaryParcelID) REFERENCES Parcel(ParcelID),
    CONSTRAINT FK_Project_Jurisdiction FOREIGN KEY (JurisdictionID)  REFERENCES Jurisdiction(JurisdictionID)
);

-- Many-to-many junction: which AllocationRights were consumed for which Project
CREATE TABLE ProjectAllocationRight (
    ProjectID          INT NOT NULL,
    AllocationRightID  INT NOT NULL,
    PRIMARY KEY (ProjectID, AllocationRightID),
    CONSTRAINT FK_PAR_Project FOREIGN KEY (ProjectID)         REFERENCES ResidentialProject(ProjectID),
    CONSTRAINT FK_PAR_Right   FOREIGN KEY (AllocationRightID) REFERENCES AllocationRight(AllocationRightID)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. QA CORRECTION EVENT
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE QaCorrectionEvent (
    QaCorrectionEventID         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ChangeEventID               INT          NOT NULL UNIQUE,    -- preserved from the notebook output for traceability
    RawAPN                      VARCHAR(15)  NOT NULL,
    CanonicalAPN                VARCHAR(15)  NOT NULL,
    CommodityShortName          VARCHAR(40)  NOT NULL,
    Year                        INT          NULL,
    PreviousQuantity            FLOAT        NULL,
    NewQuantity                 FLOAT        NULL,
    QuantityDelta               INT          NULL,
    ChangeSource                VARCHAR(40)  NULL,
    Rationale                   VARCHAR(500) NULL,
    EvidenceURL                 VARCHAR(500) NULL,
    RecordedBy                  VARCHAR(50)  NULL,
    RecordedAt                  DATETIME2    NOT NULL,
    ReportingYear               INT          NULL,
    SweepCampaign               VARCHAR(40)  NULL,
    CorrectionCategory          VARCHAR(200) NULL,
    CorrectionCategoryCanonical BIT          NULL,
    SummaryReason               VARCHAR(500) NULL,
    SourceFileSnapshot          VARCHAR(120) NULL,
    LoadedDate                  DATE         NOT NULL DEFAULT CONVERT(DATE, SYSUTCDATETIME())
);
CREATE INDEX IX_Qa_CanonicalAPN ON QaCorrectionEvent(CanonicalAPN);
CREATE INDEX IX_Qa_ReportingYear ON QaCorrectionEvent(ReportingYear);


-- ─────────────────────────────────────────────────────────────────────────────
-- SEED DATA (run after table creation)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO Commodity (CommodityCode, Commodity, Unit, BasePlanEra) VALUES
    ('RES', 'Residential allocations',     'units',  '1987'),
    ('RBU', 'Residential bonus units',     'units',  '1987'),
    ('CFA', 'Commercial floor area',       'sq ft',  '1987'),
    ('TAU', 'Tourist accommodation units', 'units',  '1987');

INSERT INTO Jurisdiction (JurisdictionCode, JurisdictionName, IsTrpaManaged) VALUES
    ('PL',   'Placer County',            0),
    ('SLT',  'City of South Lake Tahoe', 0),
    ('WA',   'Washoe County',            0),
    ('DG',   'Douglas County',           0),
    ('EL',   'El Dorado County',         0),
    ('TRPA', 'Tahoe Regional Planning Agency', 1);


-- ─────────────────────────────────────────────────────────────────────────────
-- END
-- ─────────────────────────────────────────────────────────────────────────────
-- Views that derive the current REST layers from these tables are in
-- erd/canonical_views.sql (companion file; one view per current snapshot layer).
