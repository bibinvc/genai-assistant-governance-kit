/**
 * Google Sheets + Gemini: classify supplier emails and prepare draft replies.
 * Sheet columns: A = email text, B = category, C = draft reply, D = security alert, E = validated by.
 *
 * Setup (not run by the author): Extensions > Apps Script, paste this file, then
 * Project Settings > Script properties: GEMINI_API_KEY and GEMINI_MODEL.
 * Only use with a Google Workspace setup approved by IT. Nothing is sent by email:
 * a person reads column C and signs column E.
 */

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Assistant IA')
    .addItem('Traiter les nouvelles lignes', 'processRows')
    .addToUi();
}

/** Masks personal data before anything leaves the spreadsheet. */
function maskPersonalData(text) {
  return text
    .replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, '[EMAIL]')
    .replace(/\b[A-Z]{2}\d{2}( ?[A-Z0-9]{4}){3,7}( ?[A-Z0-9]{1,3})?\b/g, '[IBAN]')
    .replace(/(\+33[ .]?|0)[1-9]([ .-]?\d{2}){4}/g, '[TEL]');
}

function bankChangeAlert(text) {
  return /(nouveau|nouvel|changement de|modification de)\s+(compte|rib|iban|coordonn[ée]es bancaires)/i.test(text)
    ? 'Changement de coordonnées bancaires : vérifier par téléphone avant toute modification.'
    : '';
}

function callGemini(systemText, userText) {
  const props = PropertiesService.getScriptProperties();
  const model = props.getProperty('GEMINI_MODEL');
  const url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent';
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'x-goog-api-key': props.getProperty('GEMINI_API_KEY') },
    payload: JSON.stringify({
      systemInstruction: { parts: [{ text: systemText }] },
      contents: [{ role: 'user', parts: [{ text: userText }] }],
      generationConfig: { temperature: 0.2 }
    }),
    muteHttpExceptions: true
  });
  if (response.getResponseCode() !== 200) {
    throw new Error('Gemini HTTP ' + response.getResponseCode());
  }
  const data = JSON.parse(response.getContentText());
  return data.candidates[0].content.parts.map(function (p) { return p.text || ''; }).join('').trim();
}

function processRows() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const rows = sheet.getDataRange().getValues();
  for (let i = 1; i < rows.length; i++) {          // row 1 = headers
    const email = String(rows[i][0] || '');
    if (!email || rows[i][1]) continue;            // empty or already processed
    const masked = maskPersonalData(email);
    let category = callGemini(
      'Classe cet e-mail fournisseur : retard, facture, qualite ou autre. Réponds par un seul mot.', masked
    ).toLowerCase();
    if (['retard', 'facture', 'qualite', 'autre'].indexOf(category) < 0) category = 'autre';
    const draft = callGemini(
      'Rédige une réponse courte et polie au nom du Service Achats. Ne promets ni date ni montant. ' +
      'Garde les éléments masqués entre crochets.', masked
    );
    sheet.getRange(i + 1, 2, 1, 3).setValues([[category, draft + '\n\n(Brouillon généré par IA, à valider)', bankChangeAlert(email)]]);
  }
}
