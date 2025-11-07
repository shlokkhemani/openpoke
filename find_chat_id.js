#!/usr/bin/env node

/**
 * Script to find the chatId for Alyn's conversation
 */

import { IMessageSDK } from '@photon-ai/imessage-kit';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

dotenv.config({ path: join(__dirname, '.env') });

const sdk = new IMessageSDK({
  debug: true,
  concurrency: 5,
  timeout: 30000
});

console.log('🔍 Searching for messages with "Salut"...\n');

try {
  const result = await sdk.getMessages({
    limit: 100,
    excludeOwnMessages: false
  });
  const messages = result.messages || result || [];

  console.log(`Found ${messages.length} total messages\n`);

  // Find messages containing "Salut"
  const salutMessages = messages.filter(msg =>
    msg.text && msg.text.toLowerCase().includes('salut')
  );

  console.log(`Found ${salutMessages.length} messages with "Salut":\n`);
  console.log('='.repeat(80));

  salutMessages.forEach((msg, idx) => {
    console.log(`\n${idx + 1}. Message ID: ${msg.id}`);
    console.log(`   Text: "${msg.text}"`);
    console.log(`   Sender: ${msg.sender}`);
    console.log(`   ChatId: "${msg.chatId}"`);
    console.log(`   isFromMe: ${msg.isFromMe}`);
    console.log(`   Date: ${msg.date.toLocaleString()}`);
    console.log(`   Service: ${msg.service}`);
  });

  console.log('\n' + '='.repeat(80));

  // Find unique chatIds
  const uniqueChats = [...new Set(salutMessages.map(m => m.chatId))];
  console.log(`\nUnique ChatIds in these messages:`);
  uniqueChats.forEach(chatId => {
    console.log(`  - "${chatId}"`);
  });

} catch (error) {
  console.error('Error:', error);
}

await sdk.close();
process.exit(0);
