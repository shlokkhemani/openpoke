#!/usr/bin/env node

/**
 * Debug script to inspect the actual structure of messages from iMessage SDK
 */

import { IMessageSDK } from '@photon-ai/imessage-kit';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load .env file
dotenv.config({ path: join(__dirname, '.env') });

const sdk = new IMessageSDK({
  debug: true,
  concurrency: 5,
  timeout: 30000
});

console.log('🔍 Fetching recent messages...\n');

try {
  const result = await sdk.getMessages({ limit: 10 });
  const messages = result.messages || result || [];

  console.log(`Found ${messages.length} messages\n`);
  console.log('='*80);

  messages.forEach((msg, idx) => {
    console.log(`\nMessage ${idx + 1}:`);
    console.log('-'.repeat(80));
    console.log(JSON.stringify(msg, null, 2));
    console.log('-'.repeat(80));
  });

} catch (error) {
  console.error('Error:', error);
}

process.exit(0);
