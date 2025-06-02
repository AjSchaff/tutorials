-- Create the schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS mydb;

-- Create the table if it doesn't exist
CREATE TABLE IF NOT EXISTS mydb.google_api_key (
    id SERIAL PRIMARY KEY,
    api_key VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create a trigger to update the updated_at timestamp
CREATE OR REPLACE FUNCTION mydb.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_google_api_key_updated_at
    BEFORE UPDATE ON mydb.google_api_key
    FOR EACH ROW
    EXECUTE FUNCTION mydb.update_updated_at_column();

-- Insert the API key
INSERT INTO mydb.google_api_key (api_key)
VALUES ('AIzaSyBo9jLDlMwV7kKSg_i7RMLAbYoKdbAa5hU')
ON CONFLICT (id) DO UPDATE
SET api_key = EXCLUDED.api_key; 