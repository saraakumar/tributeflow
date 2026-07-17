/**
 * TributeFlow "Publish to Wall" button for the Google Sheet.
 *
 * What it does when staff click Publish:
 *   1. Reads the Pet and People tabs and commits them as incoming/sheet_data.json
 *      to the pipeline repo (so the pipeline never needs Google credentials).
 *   2. Fires a repository_dispatch that runs the publish workflow.
 *   3. Schedules a check a few minutes later that reads last_run_summary.json
 *      from the repo and emails it to staff via MailApp — sent from the account
 *      of whoever clicked Publish, so no SMTP credentials exist anywhere.
 *
 * Setup (once):
 * 1. In the Google Sheet: Extensions -> Apps Script, paste this file.
 * 2. Project Settings -> Script Properties, add:
 *      GITHUB_REPO   e.g. "yourname/tributeflow"  (the pipeline repo)
 *      GITHUB_TOKEN  a fine-grained PAT with Contents: read/write on that repo
 *      RECIPIENTS    e.g. "development@caspca.org,comms@caspca.org"
 * 3. Reload the sheet — a "Tribute Wall" menu appears. The first click asks
 *    each user once for permission to read the sheet and send email as them.
 */

var TABS = ['Pet', 'People'];          // sheet tab -> wall mapping below
var WALL_FOR_TAB = { 'Pet': 'pets', 'People': 'people' };
var SUMMARY_PATH = 'last_run_summary.json';
var DATA_PATH = 'incoming/sheet_data.json';
var MAX_EMAIL_CHECKS = 5;              // ~15 minutes of retries, 3 min apart

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

  // 1. Snapshot the sheet tabs into the repo (fixture format: {wall: values grid})
  var data = {};
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  for (var i = 0; i < TABS.length; i++) {
    var sheet = ss.getSheetByName(TABS[i]);
    if (!sheet) {
      ui.alert('Could not find a tab named "' + TABS[i] + '". Was it renamed? ' +
               'Publishing was cancelled — nothing changed.');
      return;
    }
    data[WALL_FOR_TAB[TABS[i]]] = sheet.getDataRange().getDisplayValues();
  }
  if (!putFile_(repo, token, DATA_PATH, JSON.stringify(data),
                'Sheet snapshot from Publish to Wall')) {
    ui.alert('Could not send the sheet data to GitHub. Please try again, or ' +
             'contact your admin if it keeps failing.');
    return;
  }

  // 2. Kick off the publish workflow
  var response = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: githubHeaders_(token),
    payload: JSON.stringify({ event_type: 'publish' }),
    muteHttpExceptions: true
  });

  if (response.getResponseCode() !== 204) {
    ui.alert('Something went wrong starting the publish (code ' +
             response.getResponseCode() + '). Please try again, or contact ' +
             'your admin if it keeps failing.');
    return;
  }

  // 3. Arrange the summary email: remember when we dispatched, then check back
  var userProps = PropertiesService.getUserProperties();
  userProps.setProperty('TF_DISPATCHED_AT', new Date().toISOString());
  userProps.setProperty('TF_EMAIL_CHECKS', '0');
  clearEmailTriggers_();
  ScriptApp.newTrigger('emailSummaryWhenReady').timeBased().after(3 * 60 * 1000).create();

  ui.alert('Publishing! The wall will update in a few minutes, and a summary ' +
           'of what published will be emailed to staff shortly after.');
}

/** Runs on a timer after publish: email the summary once the run has finished. */
function emailSummaryWhenReady() {
  var props = PropertiesService.getScriptProperties();
  var userProps = PropertiesService.getUserProperties();
  var repo = props.getProperty('GITHUB_REPO');
  var token = props.getProperty('GITHUB_TOKEN');
  var recipients = props.getProperty('RECIPIENTS') || '';
  var dispatchedAt = userProps.getProperty('TF_DISPATCHED_AT');
  var checks = parseInt(userProps.getProperty('TF_EMAIL_CHECKS') || '0', 10) + 1;
  userProps.setProperty('TF_EMAIL_CHECKS', String(checks));

  var summary = getFileJson_(repo, token, SUMMARY_PATH);
  var fresh = summary && dispatchedAt && summary.completed_at > dispatchedAt;

  if (!fresh) {
    clearEmailTriggers_();
    if (checks < MAX_EMAIL_CHECKS) {
      ScriptApp.newTrigger('emailSummaryWhenReady').timeBased().after(3 * 60 * 1000).create();
    } else if (recipients) {
      MailApp.sendEmail(recipients, 'Tribute wall publish — no summary yet',
        'A publish was started from the Google Sheet but no result appeared ' +
        'within 15 minutes. It may still be running, or it may have failed — ' +
        'please check with your admin.\n\n(Automated message from TributeFlow.)');
    }
    return;
  }

  clearEmailTriggers_();
  if (recipients) {
    MailApp.sendEmail(recipients, summary.subject, summary.body);
  }
}

function clearEmailTriggers_() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'emailSummaryWhenReady') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
}

function githubHeaders_(token) {
  return {
    'Authorization': 'Bearer ' + token,
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
  };
}

/** Create or update a file in the repo via the Contents API. Returns success. */
function putFile_(repo, token, path, content, message) {
  var url = 'https://api.github.com/repos/' + repo + '/contents/' + path;
  var body = {
    message: message,
    content: Utilities.base64Encode(content, Utilities.Charset.UTF_8)
  };
  var existing = UrlFetchApp.fetch(url, {
    headers: githubHeaders_(token), muteHttpExceptions: true
  });
  if (existing.getResponseCode() === 200) {
    body.sha = JSON.parse(existing.getContentText()).sha;
  }
  var resp = UrlFetchApp.fetch(url, {
    method: 'put',
    contentType: 'application/json',
    headers: githubHeaders_(token),
    payload: JSON.stringify(body),
    muteHttpExceptions: true
  });
  return resp.getResponseCode() === 200 || resp.getResponseCode() === 201;
}

/** Fetch and parse a JSON file from the repo, or null if unavailable. */
function getFileJson_(repo, token, path) {
  var resp = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + repo + '/contents/' + path,
    { headers: githubHeaders_(token), muteHttpExceptions: true });
  if (resp.getResponseCode() !== 200) return null;
  var decoded = Utilities.newBlob(
    Utilities.base64Decode(JSON.parse(resp.getContentText()).content.replace(/\n/g, ''))
  ).getDataAsString();
  try { return JSON.parse(decoded); } catch (e) { return null; }
}
