-- Create the analyst_app database and starter roles.
CREATE DATABASE analyst_app;

CREATE USER data_analyst_ro WITH PASSWORD 'data_analyst_ro';
CREATE USER data_analyst_app WITH PASSWORD 'data_analyst_app';

ALTER DATABASE analyst_app OWNER TO data_analyst_app;

GRANT CONNECT ON DATABASE meta_ads_demo TO data_analyst_ro;
GRANT CONNECT ON DATABASE analyst_app TO data_analyst_app;
