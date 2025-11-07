#!/usr/bin/env node

/**
 * Test decoding attributed body from iMessage database
 */

import Database from 'better-sqlite3';
import { homedir } from 'os';
import { join } from 'path';

const IMESSAGE_DB_PATH = join(homedir(), 'Library', 'Messages', 'chat.db');
const db = new Database(IMESSAGE_DB_PATH, { readonly: true });

// Get the most recent message with attributed body
const query = `
  SELECT
    m.ROWID as id,
    m.text,
    m.attributedBody,
    hex(m.attributedBody) as hex_body,
    length(m.attributedBody) as body_length
  FROM message m
  WHERE m.ROWID = 150013
`;

const row = db.prepare(query).get();

console.log('Message ID:', row.id);
console.log('Text field:', row.text);
console.log('Body length:', row.body_length);
console.log('\nHex dump (first 500 chars):');
console.log(row.hex_body.substring(0, 500));

console.log('\n\nRaw buffer (first 200 bytes as string):');
if (row.attributedBody) {
  const buf = row.attributedBody;
  console.log(buf.toString('utf8', 0, Math.min(200, buf.length)));

  console.log('\n\nSearching for text in buffer...');
  const str = buf.toString('utf8');

  // Try different patterns
  const patterns = [
    /HALLO/gi,
    /ALALALALLA/gi,
    /Salut/gi
  ];

  patterns.forEach(pattern => {
    const matches = str.match(pattern);
    if (matches) {
      console.log(`Found "${pattern}":`, matches);

      // Get context around match
      const index = str.search(pattern);
      const before = str.substring(Math.max(0, index - 50), index);
      const after = str.substring(index, Math.min(str.length, index + 100));

      console.log('Context:', before.replace(/[\x00-\x1F\x7F-\x9F]/g, '.') + '[MATCH]' + after.replace(/[\x00-\x1F\x7F-\x9F]/g, '.'));
    }
  });

  // Try to find all printable text
  console.log('\n\nAll printable strings (length > 3):');
  const printable = str.match(/[\x20-\x7E]{4,}/g);
  if (printable) {
    printable.forEach((s, i) => {
      if (i < 20) { // Show first 20
        console.log(`  ${i + 1}. "${s}"`);
      }
    });
  }
}

db.close();
