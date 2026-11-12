/* DEV ONLY. Recreates the production server tables (T_IIR_ARIF_*) with exactly the same names, columns
   and types, so code developed here runs unchanged on the server. Source: docs/schema/db_structure_server.txt.

   NEVER run this on the server: there the tables already exist and are owned by the data pipeline.
   Run:  sqlcmd -S localhost -E -d recruitment -i sql\01_dev_server_tables.sql
   Then: .venv\Scripts\python -m scripts.seed_dev_db   (fake data)
*/
SET NOCOUNT ON;
IF DB_NAME() IN ('master', 'model', 'msdb', 'tempdb') THROW 50000, 'Run this in the dev database (recruitment).', 1;

IF OBJECT_ID('dbo.T_IIR_ARIF_SKILLS') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_SKILLS;
IF OBJECT_ID('dbo.T_IIR_ARIF_EXPERIENCE') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_EXPERIENCE;
IF OBJECT_ID('dbo.T_IIR_ARIF_EDUCATION') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_EDUCATION;
IF OBJECT_ID('dbo.T_IIR_ARIF_CANDIDATE') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_CANDIDATE;

CREATE TABLE dbo.T_IIR_ARIF_CANDIDATE (
    ARIF_ID                     int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CANDIDATE_ID                int            NOT NULL,
    GIVENNAME                   nvarchar(300)  NULL,
    MIDDLENAME                  nvarchar(300)  NULL,
    SURNAME                     nvarchar(300)  NULL,
    CREATED_ON                  date           NULL DEFAULT (getdate()),
    CURRENT_EMPLOYER            nvarchar(300)  NULL,
    CURRENT_JOB_TITLE           nvarchar(300)  NULL,
    YEARS_OF_EXPERIENCE         nvarchar(300)  NULL,
    COUNTRY                     nvarchar(300)  NULL,
    NATIONAL_ID                 nvarchar(300)  NULL,
    SAUDI_EXPAT                 nvarchar(300)  NULL,
    GPA                         nvarchar(300)  NULL,
    LAST_MODIFIED               date           NULL,
    SOURCE_OF_APPLICATION       nvarchar(300)  NULL,
    GENDER                      nvarchar(30)   NULL,
    HIGHEST_JOB_REQ_ID          nvarchar(255)  NULL,
    HIGHEST_APPLICATION_ID      nvarchar(255)  NULL,
    HIGHEST_APPLICATION_STATUS  nvarchar(255)  NULL,
    APPLICATION_STATUS_CODE     int            NULL,
    RESUME_UPLOADED             int            NULL,
    RESUME_DATE                 date           NULL,
    RESUME_FILE_TYPE            nvarchar(30)   NULL,
    RESUME_PROCESSED            int            NULL,
    EDUCATION_EXTRACTED         int            NULL,
    EXPERIENCE_EXTRACTED        int            NULL,
    SKILLS_EXTRACTED            int            NULL,
    SUMMARY_EXTRACTED           int            NULL,
    WILD_SEARCH_EXTRACTED       int            NULL,
    CANDIDATE_FLAG              nvarchar(255)  NULL,
    INDREASON                   nvarchar(30)   NULL,
    NUMREASON                   nvarchar(30)   NULL,
    VERBREASON                  nvarchar(30)   NULL,
    SUMMARY                     nvarchar(max)  NULL,
    TEXT_TOKENS                 nvarchar(max)  NULL
);

CREATE TABLE dbo.T_IIR_ARIF_EDUCATION (
    SCHOOL_ID         int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ARIF_ID           int            NOT NULL,
    CANDIDATE_ID      int            NOT NULL,
    DEGREE            nvarchar(300)  NULL,
    MAJOR             nvarchar(300)  NULL,
    INSTITUTION       nvarchar(300)  NULL,
    STARTDATE         nvarchar(300)  NULL,
    ENDDATE           nvarchar(300)  NULL,
    NORM_DEGREE       nvarchar(300)  NULL,
    NORM_INSTITUTION  nvarchar(300)  NULL,
    NORM_STARTDATE    date           NULL,
    NORM_ENDDATE      date           NULL
);

CREATE TABLE dbo.T_IIR_ARIF_EXPERIENCE (
    JOB_ID               int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ARIF_ID              int            NOT NULL,
    CANDIDATE_ID         int            NOT NULL,
    TITLE                nvarchar(300)  NULL,
    EMPLOYER             nvarchar(300)  NULL,
    STARTDATE            nvarchar(300)  NULL,
    ENDDATE              nvarchar(300)  NULL,
    COUNTRY              nvarchar(300)  NULL,
    YEARS_OF_EXPERIENCE  int            NULL,
    NORM_TITLE           nvarchar(300)  NULL,
    NORM_EMPLOYER        nvarchar(300)  NULL,
    NORM_STARTDATE       date           NULL,
    NORM_ENDDATE         date           NULL
);

CREATE TABLE dbo.T_IIR_ARIF_SKILLS (
    SKILL_ID      int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ARIF_ID       int            NOT NULL,
    CANDIDATE_ID  int            NOT NULL,
    ORG_SKILL     nvarchar(300)  NULL,
    NORM_SKILL    nvarchar(300)  NULL
);

PRINT 'T_IIR_ARIF_* dev tables created.';
