-- =============================================================================
-- Derived views: every current REST layer as a SQL view over the canonical schema
-- =============================================================================
-- Designed 2026-05-15. Companion to erd/canonical_schema_ddl.sql.
-- Every current snapshot REST layer in Cumulative_Accounting becomes one of
-- these views. Publishing the views as REST replaces the snapshot tables
-- (Layers 10/11/12/13/14/15/16) with always-fresh derivations.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- v_AllocationsBalances - replaces Layer 10 (snapshot)
-- 12 rows: 3 Sources (Grand Total, 1987 RP, 2012 RP) x 4 Commodities
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_AllocationsBalances AS
WITH eras AS (
    SELECT 'Grand Total'        AS SourceLabel, CAST(NULL AS VARCHAR(10)) AS FilterEra
    UNION ALL SELECT '1987 Regional Plan', '1987'
    UNION ALL SELECT '2012 Regional Plan', '2012'
)
SELECT
    eras.SourceLabel                                                                              AS [Source],
    c.Commodity                                                                                   AS Commodity,
    c.CommodityCode                                                                               AS CommodityCode,
    SUM(ar.Quantity)                                                                              AS TotalAuthorized,
    SUM(CASE WHEN ar.CurrentStatus = 'Allocated'  THEN ar.Quantity ELSE 0 END)                    AS AllocatedToPrivate,
    SUM(CASE WHEN ar.CurrentStatus = 'InPool'     THEN ar.Quantity ELSE 0 END)                    AS JurisdictionPool,
    SUM(CASE WHEN ar.CurrentStatus = 'TRPAPool'   THEN ar.Quantity ELSE 0 END)                    AS TRPAPool,
    SUM(CASE WHEN ar.CurrentStatus = 'Unreleased' THEN ar.Quantity ELSE 0 END)                    AS Unreleased,
    SUM(CASE WHEN ar.CurrentStatus IN ('InPool','TRPAPool','Unreleased') THEN ar.Quantity ELSE 0 END) AS TotalBalanceRemaining
FROM AllocationRight ar
CROSS JOIN eras
JOIN Commodity c ON ar.CommodityCode = c.CommodityCode
WHERE eras.FilterEra IS NULL OR ar.PlanEra = eras.FilterEra
GROUP BY eras.SourceLabel, c.Commodity, c.CommodityCode;
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- v_ResidentialAdditionsBySource - replaces Layer 11 (snapshot)
-- 98 rows: 14 years x 7 source/direction combos
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_ResidentialAdditionsBySource AS
-- Added units: events that resulted in 'Allocated' status for RES commodity
SELECT
    YEAR(ae.EventDate)        AS [Year],
    'Added'                   AS Direction,
    CASE
        WHEN ar.CommodityCode = 'RBU' AND ae.EventType = 'Assignment' THEN 'Bonus Units'
        WHEN ae.EventType = 'Assignment'                              THEN 'Allocations'
        WHEN ae.EventType = 'Transfer'                                THEN 'Transfers'
        WHEN ae.EventType = 'Conversion'                              THEN 'Conversions'
        WHEN ae.EventType = 'Withdraw'                                THEN 'Banked'
        ELSE 'Other'
    END                       AS [Source],
    SUM(ae.QuantityAffected)  AS Units
FROM AllocationEvent ae
JOIN AllocationRight ar ON ae.AllocationRightID = ar.AllocationRightID
WHERE ar.CommodityCode IN ('RES','RBU')
  AND ae.EventType IN ('Assignment','Transfer','Conversion','Withdraw')
  AND ae.ToStatus = 'Allocated'
GROUP BY YEAR(ae.EventDate),
    CASE
        WHEN ar.CommodityCode = 'RBU' AND ae.EventType = 'Assignment' THEN 'Bonus Units'
        WHEN ae.EventType = 'Assignment'                              THEN 'Allocations'
        WHEN ae.EventType = 'Transfer'                                THEN 'Transfers'
        WHEN ae.EventType = 'Conversion'                              THEN 'Conversions'
        WHEN ae.EventType = 'Withdraw'                                THEN 'Banked'
        ELSE 'Other'
    END

UNION ALL

-- Removed units: events that took units OUT of 'Allocated' status (negative)
SELECT
    YEAR(ae.EventDate)         AS [Year],
    'Removed'                  AS Direction,
    CASE
        WHEN ae.EventType = 'Bank'        THEN 'Banked'
        WHEN ae.EventType = 'Conversion'  THEN 'Converted'
        ELSE 'Other'
    END                        AS [Source],
    -SUM(ae.QuantityAffected)  AS Units
FROM AllocationEvent ae
JOIN AllocationRight ar ON ae.AllocationRightID = ar.AllocationRightID
WHERE ar.CommodityCode IN ('RES','RBU')
  AND ae.EventType IN ('Bank','Conversion')
  AND ae.FromStatus = 'Allocated'
GROUP BY YEAR(ae.EventDate),
    CASE
        WHEN ae.EventType = 'Bank'        THEN 'Banked'
        WHEN ae.EventType = 'Conversion'  THEN 'Converted'
        ELSE 'Other'
    END;
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- v_PoolBalances - replaces Layer 12 (snapshot)
-- 26 rows: 4 commodities x per-pool (Combined plan-era)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_PoolBalances AS
SELECT
    c.Commodity                                                                                       AS Commodity,
    c.CommodityCode                                                                                   AS CommodityCode,
    'Combined'                                                                                        AS Plan,
    p.PoolName                                                                                        AS Pool,
    p.PoolType                                                                                        AS [Group],
    SUM(ar.Quantity)                                                                                  AS RegionalPlanMaximum,
    SUM(CASE WHEN ar.CurrentStatus = 'Allocated' THEN ar.Quantity ELSE 0 END)                         AS AssignedToProjects,
    SUM(CASE WHEN ar.CurrentStatus IN ('InPool','TRPAPool','Unreleased') THEN ar.Quantity ELSE 0 END) AS NotAssigned
FROM DevelopmentRightPool p
LEFT JOIN AllocationRight ar
    ON ar.CurrentPoolID = p.PoolID
    OR (ar.CurrentStatus = 'Allocated' AND EXISTS (
        -- Reverse-trace: an Allocated right belongs to a pool via its most recent
        -- pool exit. Practical impl: keep ar.OriginPoolID denormalized for speed,
        -- or join via the latest AllocationEvent.ToPoolID = p.PoolID for that right.
        SELECT 1 FROM AllocationEvent ae
        WHERE ae.AllocationRightID = ar.AllocationRightID
          AND ae.FromPoolID = p.PoolID
        AND ae.EventDate = (SELECT MAX(EventDate) FROM AllocationEvent WHERE AllocationRightID = ar.AllocationRightID AND FromPoolID IS NOT NULL)
    ))
JOIN Commodity c ON p.CommodityCode = c.CommodityCode
GROUP BY c.Commodity, c.CommodityCode, p.PoolName, p.PoolType;
GO

-- NOTE: the LEFT JOIN above is intentionally tricky. Simpler implementations:
--   (a) keep ar.OriginPoolID as a denormalized field on AllocationRight (set
--       once at Issuance, never updated) and join on that. Trades a tiny bit
--       of storage for query simplicity.
--   (b) materialize this view nightly (SQL Server: indexed view) so per-query
--       cost stays low.
-- The view above is "logically correct"; production should pick (a) or (b).


-- ─────────────────────────────────────────────────────────────────────────────
-- v_ResidentialProjects - replaces Layer 13 (snapshot)
-- Just SELECT from the table directly
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_ResidentialProjects AS
SELECT
    rp.YearCompleted                  AS [Year],
    rp.ProjectName                    AS ProjectName,
    rp.TotalUnits                     AS Units,
    -- Notes: synthesize the analyst's narrative form from the structured fields
    CASE
        WHEN rp.AffordableUnits > 0 AND rp.ModerateUnits > 0
            THEN CAST(rp.AffordableUnits AS VARCHAR) + ' affordable, ' + CAST(rp.ModerateUnits AS VARCHAR) + ' moderate'
        WHEN rp.AffordableUnits > 0
            THEN CAST(rp.AffordableUnits AS VARCHAR) + ' affordable'
        WHEN rp.AchievableUnits > 0
            THEN CAST(rp.AchievableUnits AS VARCHAR) + ' achievable'
        ELSE ''
    END                               AS Notes,
    rp.ProjectName + ': ' + CAST(rp.TotalUnits AS VARCHAR) + ' units'
        + CASE WHEN rp.AffordableUnits + rp.ModerateUnits + rp.AchievableUnits > 0
               THEN ' (' + CASE
                   WHEN rp.AffordableUnits > 0 AND rp.ModerateUnits > 0
                       THEN CAST(rp.AffordableUnits AS VARCHAR) + ' affordable, ' + CAST(rp.ModerateUnits AS VARCHAR) + ' moderate'
                   WHEN rp.AffordableUnits > 0
                       THEN CAST(rp.AffordableUnits AS VARCHAR) + ' affordable'
                   WHEN rp.AchievableUnits > 0
                       THEN CAST(rp.AchievableUnits AS VARCHAR) + ' achievable'
                   ELSE ''
               END + ')'
               ELSE ''
          END                         AS Description
FROM ResidentialProject rp;
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- v_ReservedNotConstructed - replaces Layer 14 (snapshot)
-- 3 rows, one per commodity
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_ReservedNotConstructed AS
SELECT
    c.Commodity                       AS Commodity,
    c.CommodityCode                   AS CommodityCode,
    SUM(ar.Quantity)                  AS Units,
    c.Unit                            AS [Unit]
FROM AllocationRight ar
JOIN Commodity c ON ar.CommodityCode = c.CommodityCode
WHERE ar.CurrentStatus = 'Allocated'
  AND ar.ConstructionStatus IN ('NotStarted','InProgress')
  AND c.CommodityCode IN ('RES','CFA','TAU')   -- RBU rolls into RES per Ken's framing
GROUP BY c.Commodity, c.CommodityCode, c.[Unit];
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- v_PoolBalancesMetering - replaces Layer 15 (snapshot)
-- ~853 rows: per-pool per-year per-direction (RES only today; extendable)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_PoolBalancesMetering AS
SELECT
    c.Commodity                                                  AS Commodity,
    c.CommodityCode                                              AS CommodityCode,
    COALESCE(pf.PoolName, pt.PoolName)                           AS Pool,
    YEAR(ae.EventDate)                                           AS [Year],
    CASE
        WHEN ae.ToStatus IN ('InPool','TRPAPool') AND ae.FromStatus IS NULL                    THEN 'Released'
        WHEN ae.ToStatus = 'Allocated' AND ae.FromStatus IN ('InPool','TRPAPool')              THEN 'Assigned'
        WHEN ae.FromStatus IN ('InPool','TRPAPool') AND ae.ToStatus = 'Unreleased'             THEN 'Unreleased'
        WHEN ae.ToStatus IN ('InPool','TRPAPool') AND ae.FromStatus IN ('InPool','TRPAPool')   THEN 'NotAssigned'
        ELSE 'Other'
    END                                                          AS Direction,
    SUM(ae.QuantityAffected)                                     AS Units
FROM AllocationEvent ae
JOIN AllocationRight ar ON ae.AllocationRightID = ar.AllocationRightID
LEFT JOIN DevelopmentRightPool pf ON ae.FromPoolID = pf.PoolID
LEFT JOIN DevelopmentRightPool pt ON ae.ToPoolID   = pt.PoolID
JOIN Commodity c ON ar.CommodityCode = c.CommodityCode
WHERE c.CommodityCode = 'RES'
GROUP BY c.Commodity, c.CommodityCode, COALESCE(pf.PoolName, pt.PoolName), YEAR(ae.EventDate),
    CASE
        WHEN ae.ToStatus IN ('InPool','TRPAPool') AND ae.FromStatus IS NULL                    THEN 'Released'
        WHEN ae.ToStatus = 'Allocated' AND ae.FromStatus IN ('InPool','TRPAPool')              THEN 'Assigned'
        WHEN ae.FromStatus IN ('InPool','TRPAPool') AND ae.ToStatus = 'Unreleased'             THEN 'Unreleased'
        WHEN ae.ToStatus IN ('InPool','TRPAPool') AND ae.FromStatus IN ('InPool','TRPAPool')   THEN 'NotAssigned'
        ELSE 'Other'
    END;
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- v_QaCorrections - replaces Layer 16 (snapshot)
-- Just SELECT from the table directly
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_QaCorrections AS
SELECT * FROM QaCorrectionEvent;
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- v_BankedByJurisdiction - replaces Layer 9 (current LIVE; restate as derived)
-- 24 rows: 6 jurisdictions x 4 commodities (residential = MFRUU + SFRUU)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR ALTER VIEW v_BankedByJurisdiction AS
SELECT
    j.JurisdictionName               AS Jurisdiction,
    c.CommodityCode                  AS Commodity,
    SUM(br.Quantity)                 AS Value
FROM BankedDevelopmentRight br
JOIN Parcel       p ON br.ParcelID      = p.ParcelID
JOIN Jurisdiction j ON p.JurisdictionID = j.JurisdictionID
JOIN Commodity    c ON br.CommodityCode = c.CommodityCode
WHERE br.Status = 'Active'
GROUP BY j.JurisdictionName, c.CommodityCode;
GO


-- =============================================================================
-- PUBLISHING
-- =============================================================================
-- After creating the views, register them with the ArcGIS Server source mxd/aprx
-- and republish Cumulative_Accounting. Each view becomes a non-spatial REST
-- table at a new layer ID (17-23 if we shadow rather than replace):
--
--   /17 v_AllocationsBalances      -> shadows Layer 10
--   /18 v_ResidentialAdditionsBySource -> shadows Layer 11
--   /19 v_PoolBalances             -> shadows Layer 12
--   /20 v_ResidentialProjects      -> shadows Layer 13
--   /21 v_ReservedNotConstructed   -> shadows Layer 14
--   /22 v_PoolBalancesMetering     -> shadows Layer 15
--   /23 v_QaCorrections            -> shadows Layer 16
--
-- During cutover, dashboards keep reading the snapshot layers; once views are
-- validated against the snapshots for one full cycle, swap the URL constants
-- (single-line edit per dashboard, as we've done five times now).
-- =============================================================================
