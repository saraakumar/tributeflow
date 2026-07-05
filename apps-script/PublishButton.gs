/**
 * TributeFlow "Publish to Wall" button for the Google Sheet.
 *
 * Setup (once):
 * 1. In the Google Sheet: Extensions -> Apps Script, paste this file.
 * 2. Project Settings -> Script Properties, add:
 *      GITHUB_REPO   e.g. "yourname/tributeflow"
 *      GITHUB_TOKEN  a fine-grained PAT with Contents: read/write on that repo
 * 3. Reload the sheet — a "Tribute Wall" menu appears.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Tribute Wall')
    .addItem('Publish to Wall', 'publishToWall')
    .addToUi();
}

function publishToWall() {
  var ui = SpreadsheetApp.getUi();
  var props = PropertiesService.getScriptProperties();
  var repo = props.getProperty('GITHUB_REPO');
  var token = props.getProperty('GITHUB_TOKEN');

  if (!repo || !token) {
    ui.alert('TributeFlow is not set up yet: ask your admin to add GITHUB_REPO and ' +
             'GITHUB_TOKEN in Extensions -> Apps Script -> Project Settings.');
    return;
  }

  var response = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/vnd.github+json'
    },
    payload: JSON.stringify({ event_type: 'publish' }),
    muteHttpExceptions: true
  });

  if (response.getResponseCode() === 204) {
    ui.alert('Publishing! The wall will update in about a minute. ' +
             'Check your email for a summary of what published.');
  } else {
    ui.alert('Something went wrong (code ' + response.getResponseCode() + '). ' +
             'Please try again, or contact your admin if it keeps failing.');
  }
}
