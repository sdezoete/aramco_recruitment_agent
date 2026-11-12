/* The app's own table: per-chat state (active job spec, last shortlist). Run on DEV and on the SERVER.
   This is the ONLY table the app writes to. It holds no candidate profile data, only job specs and
   ids/scores of shortlisted candidates. Idempotent: safe to run again.

   Server (by a DBA, once):   sqlcmd -S <server> -d <database> -E -i sql\02_agent_memory.sql
   App login needs: SELECT, INSERT, UPDATE, DELETE on dbo.T_IIR_ARIF_AGENT_MEMORY only.
*/
SET NOCOUNT ON;
IF OBJECT_ID('dbo.T_IIR_ARIF_AGENT_MEMORY') IS NULL
BEGIN
    CREATE TABLE dbo.T_IIR_ARIF_AGENT_MEMORY (
        CHAT_ID       nvarchar(64)   NOT NULL,
        MEMORY_KEY    nvarchar(100)  NOT NULL,
        MEMORY_VALUE  nvarchar(max)  NULL,
        UPDATED_AT    datetime2(0)   NOT NULL CONSTRAINT DF_T_IIR_ARIF_AGENT_MEMORY_UPDATED DEFAULT (sysdatetime()),
        CONSTRAINT PK_T_IIR_ARIF_AGENT_MEMORY PRIMARY KEY (CHAT_ID, MEMORY_KEY)
    );
    CREATE INDEX IX_T_IIR_ARIF_AGENT_MEMORY_UPDATED ON dbo.T_IIR_ARIF_AGENT_MEMORY (UPDATED_AT);
    PRINT 'T_IIR_ARIF_AGENT_MEMORY created.';
END
ELSE
    PRINT 'T_IIR_ARIF_AGENT_MEMORY already exists.';
