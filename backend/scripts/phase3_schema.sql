CREATE TABLE IF NOT EXISTS notification_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type VARCHAR(30) NOT NULL,
  entity_id VARCHAR(255) NOT NULL,
  channel VARCHAR(30) NOT NULL,
  target_id VARCHAR(255) NOT NULL,
  display_name VARCHAR(255),
  is_verified BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  metadata JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_links_entity_channel
  ON notification_links (entity_type, entity_id, channel);

CREATE TABLE IF NOT EXISTS notification_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type VARCHAR(30) NOT NULL,
  entity_id VARCHAR(255) NOT NULL,
  channel VARCHAR(30) NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  delivery_status VARCHAR(30) DEFAULT 'pending',
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);
