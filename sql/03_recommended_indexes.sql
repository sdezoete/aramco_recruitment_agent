/* OPTIONAL, for the DBA: indexes that make the app fast on 350k-500k candidates.
   These touch the pipeline-owned T_IIR_ARIF_* tables, so they are a REQUEST to the table owner, not something
   the app or the release runs. Measured on dev with 100k candidates and NO indexes: matching ~1 s, search
   < 1 s; most of that time is child-table scans that these indexes remove. Idempotent.

   Run (by the DBA, after agreeing with the table owner):
     sqlcmd -S <server> -d <database> -E -i sql\03_recommended_indexes.sql
*/
SET NOCOUNT ON;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RA_SKILLS_ARIF' AND object_id = OBJECT_ID('dbo.T_IIR_ARIF_SKILLS'))
    CREATE INDEX IX_RA_SKILLS_ARIF ON dbo.T_IIR_ARIF_SKILLS (ARIF_ID) INCLUDE (ORG_SKILL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RA_SKILLS_ORG' AND object_id = OBJECT_ID('dbo.T_IIR_ARIF_SKILLS'))
    CREATE INDEX IX_RA_SKILLS_ORG ON dbo.T_IIR_ARIF_SKILLS (ORG_SKILL) INCLUDE (ARIF_ID);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RA_EXPERIENCE_ARIF' AND object_id = OBJECT_ID('dbo.T_IIR_ARIF_EXPERIENCE'))
    CREATE INDEX IX_RA_EXPERIENCE_ARIF ON dbo.T_IIR_ARIF_EXPERIENCE (ARIF_ID);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RA_EDUCATION_ARIF' AND object_id = OBJECT_ID('dbo.T_IIR_ARIF_EDUCATION'))
    CREATE INDEX IX_RA_EDUCATION_ARIF ON dbo.T_IIR_ARIF_EDUCATION (ARIF_ID);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RA_CANDIDATE_ATS' AND object_id = OBJECT_ID('dbo.T_IIR_ARIF_CANDIDATE'))
    CREATE INDEX IX_RA_CANDIDATE_ATS ON dbo.T_IIR_ARIF_CANDIDATE (CANDIDATE_ID);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RA_CANDIDATE_FILTERS' AND object_id = OBJECT_ID('dbo.T_IIR_ARIF_CANDIDATE'))
    CREATE INDEX IX_RA_CANDIDATE_FILTERS ON dbo.T_IIR_ARIF_CANDIDATE (SAUDI_EXPAT, CANDIDATE_FLAG, APPLICATION_STATUS_CODE);
PRINT 'Recommended indexes present.';
