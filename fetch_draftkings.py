function createCheatSheet() {
  // Open the specific spreadsheet by ID
  var ss = SpreadsheetApp.openById('10pr1-Q4SirA99t8lzcQ64znrAyyYInumlVCgqZIiBzA');
  
  // Get the sheets
  var combinedSheet = ss.getSheetByName('Combined');
  var playerDataSheet = ss.getSheetByName('DRAFTTABLE');
  var cheatSheet = ss.getSheetByName('CHEAT SHEET');
  var finalProjSheet = ss.getSheetByName('FINAL PROJECTIONS');
  var preseasonProjSheet = ss.getSheetByName('PRESEASON PROJ');
  
  // Create CHEAT SHEET tab if it doesn’t exist
  if (!cheatSheet) {
    cheatSheet = ss.insertSheet('CHEAT SHEET');
  }
  
  try {
    // Check if sheets exist
    if (!combinedSheet || !playerDataSheet || !finalProjSheet) {
      throw new Error("Combined, DRAFTTABLE, or FINAL PROJECTIONS sheet not found.");
    }
    
    // Check if Combined sheet has data
    var lastColumn = combinedSheet.getLastColumn();
    var lastRow = combinedSheet.getLastRow();
    if (lastColumn < 1 || lastRow < 1) {
      throw new Error("Combined sheet is empty or has no data.");
    }
    
    // Define stat type mapping with lowercase keys for case-insensitive matching (football only)
    var statTypeMapping = {
      'passing tds': 'Passing TDs',
      'pass tds': 'Passing TDs',
      'rushing': 'Rushing Yards',
      'rush': 'Rushing Yards',
      'fantasy points': 'Fantasy Score',
      'fantasy score': 'Fantasy Score',
      'player_rush_yds': 'Rushing Yards',
      'rushing yards': 'Rushing Yards',
      'passing yards': 'Passing Yards',
      'pass yards': 'Passing Yards',
      'receiving yards': 'Receiving Yards',
      'rec yards': 'Receiving Yards',
      'rush + rec yards': 'Rush+Rec Yards',
      'rush+rec yards': 'Rush+Rec Yards',
      'rush + rec tds': 'Anytime TD',
      'player_anytime_td': 'Anytime TD',
      'passing attempts': 'Passing Attempts',
      'pass attempts': 'Passing Attempts',
      'fg made': 'FG Made',
      'field goals made': 'FG Made',
      'pat made': 'PAT Made',
      'extra points made': 'PAT Made'
    };
    
    // Function to standardize player keys with enhanced normalization
    function getPlayerKey(playerName) {
      if (!playerName || typeof playerName !== 'string' || playerName.trim() === '') {
        return '';
      }
      var normalized = playerName.toString().toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/’/g, "'")
        .replace(/-/g, ' ')
        .replace(/\./g, '')
        .replace(/[^a-z' ]/g, '')
        .trim();
      normalized = normalized.replace(/\s+(jr|sr|ii|iii|iv|v|vi|vii|viii|ix|x)$/g, '').trim();
      return normalized;
    }
    
    // Normalize any date value (Date object or string) to YYYY-MM-DD
    function normalizeDate(d) {
      if (!d) return '';
      try {
        if (Object.prototype.toString.call(d) === '[object Date]' && !isNaN(d.getTime())) {
          return Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd');
        }
        var parsed = new Date(d);
        if (!isNaN(parsed.getTime())) {
          return Utilities.formatDate(parsed, Session.getScriptTimeZone(), 'yyyy-MM-dd');
        }
      } catch (e) {}
      return String(d).trim();
    }
    
    /**
     * Build a simple projected FP from whatever prop lines exist for this date.
     * Prefers the actual "Fantasy Score" prop when present.
     */
    function calculateProjectedFPFromProps(stats, position) {
      if (!stats) return 0;

      if (stats['Fantasy Score'] !== undefined && stats['Fantasy Score'] !== '') {
        var fs = parseFloat(stats['Fantasy Score']);
        if (!isNaN(fs)) return fs;
      }

      var passYds   = parseFloat(stats['Passing Yards'])   || 0;
      var passTd    = parseFloat(stats['Passing TDs'])     || 0;
      var rushYds   = parseFloat(stats['Rushing Yards'])   || 0;
      var recYds    = parseFloat(stats['Receiving Yards']) || 0;
      var rushRec   = parseFloat(stats['Rush+Rec Yards'])  || 0;
      var anytimeTd = parseFloat(stats['Anytime TD'])      || 0;

      if (rushRec > 0 && rushYds === 0 && recYds === 0) {
        rushYds = rushRec * 0.6;
        recYds  = rushRec * 0.4;
      }

      var fp = 0;
      fp += passYds * 0.04;
      fp += passTd  * 4;
      fp += rushYds * 0.1;
      fp += recYds  * 0.1;

      if (anytimeTd > 0) {
        fp += anytimeTd * 6;
      }

      return Math.round(fp * 100) / 100;
    }
    
    // Name mapping for known discrepancies
    var nameMapping = {
      'ronald holland ii': 'ron holland'
    };
    
    // ---------- Load hand projections from PRESEASON PROJ (robust multi-format) ----------
    var handProjMap = {}; // key = playerKey|date → number
    if (preseasonProjSheet) {
      var preData = preseasonProjSheet.getDataRange().getValues();
      if (preData.length > 1) {
        var preHeaders = preData[0];
        var preProjIdx    = preHeaders.indexOf('PROJECTION');
        var prePlayerIdx  = preHeaders.indexOf('Player Name');
        var preDateIdx    = preHeaders.indexOf('Date');
        var preGameStartIdx = preHeaders.indexOf('Game Start Time');
        
        if (preProjIdx !== -1 && prePlayerIdx !== -1) {
          for (var p = 1; p < preData.length; p++) {
            var prow = preData[p];
            var handVal = parseFloat(prow[preProjIdx]);
            if (isNaN(handVal) || handVal === 0) continue;
            
            var pName = prow[prePlayerIdx];
            var pKey  = getPlayerKey(pName);
            if (!pKey) continue;
            
            // Collect every possible date string we can extract
            var dateCandidates = [];
            
            if (preDateIdx !== -1 && prow[preDateIdx]) {
              dateCandidates.push(prow[preDateIdx]);
            }
            if (preGameStartIdx !== -1 && prow[preGameStartIdx]) {
              dateCandidates.push(prow[preGameStartIdx]);
            }
            
            dateCandidates.forEach(function(raw) {
              if (!raw) return;
              
              // Full normalized date (yyyy-MM-dd)
              var full = normalizeDate(raw);
              if (full) {
                handProjMap[pKey + '|' + full] = handVal;
              }
              
              // Short M/D versions
              try {
                var d = new Date(raw);
                if (!isNaN(d.getTime())) {
                  var m = d.getMonth() + 1;
                  var day = d.getDate();
                  var short1 = m + '/' + day;                               // 8/13
                  var short2 = m + '/' + ('0' + day).slice(-2);             // 8/13
                  var short3 = ('0' + m).slice(-2) + '/' + ('0' + day).slice(-2); // 08/13
                  handProjMap[pKey + '|' + short1] = handVal;
                  handProjMap[pKey + '|' + short2] = handVal;
                  handProjMap[pKey + '|' + short3] = handVal;
                }
              } catch (e) {}
              
              // Also store the raw string just in case
              handProjMap[pKey + '|' + String(raw).trim()] = handVal;
            });
          }
          Logger.log('Loaded ' + Object.keys(handProjMap).length + ' hand projection keys from PRESEASON PROJ');
        }
      }
    }
    
    // Get headers from Combined sheet
    var combinedHeaders = combinedSheet.getRange(1, 1, 1, lastColumn).getValues()[0];
    var playerNameIndex = combinedHeaders.indexOf('Player Name');
    var statTypeIndex = combinedHeaders.indexOf('Stat Type');
    var ppLineIndex = combinedHeaders.indexOf('PrizePicks Line');
    var udLineIndex = combinedHeaders.indexOf('Underdog Line');
    var combinedDateIndex = combinedHeaders.indexOf('Combined Date');
    var ppStartTimeIndex = combinedHeaders.indexOf('PrizePicks Start Time');
    var udStartTimeIndex = combinedHeaders.indexOf('Underdog Scheduled At');
    var matchTitleIndex = combinedHeaders.indexOf('Match Title (Underdog)');
    var gameShortTitleIndex = combinedHeaders.indexOf('Game Short Title (Underdog)');
    var venueNameIndex = combinedHeaders.indexOf('Venue Name (Underdog)');
    var venueTypeIndex = combinedHeaders.indexOf('Venue Type (Underdog)');
    var broadcastsIndex = combinedHeaders.indexOf('Broadcasts (Underdog)');
    
    if (playerNameIndex === -1 || statTypeIndex === -1 || combinedDateIndex === -1) {
      throw new Error("Required headers 'Player Name', 'Stat Type', or 'Combined Date' not found in Combined sheet.");
    }
    
    // Get headers from DRAFTTABLE sheet
    var playerDataLastColumn = playerDataSheet.getLastColumn();
    var playerDataLastRow = playerDataSheet.getLastRow();
    if (playerDataLastColumn < 1 || playerDataLastRow < 1) {
      throw new Error("DRAFTTABLE sheet is empty or has no data.");
    }
    var playerDataHeaders = playerDataSheet.getRange(1, 1, 1, playerDataLastColumn).getValues()[0];
    var pdPlayerNameIndex = playerDataHeaders.indexOf('Player Name');
    var positionIndex = playerDataHeaders.indexOf('Position');
    var teamIndex = playerDataHeaders.indexOf('Team');
    var salaryIndex = playerDataHeaders.indexOf('Salary');
    var draftableIdIndex = playerDataHeaders.indexOf('Draftable ID');
    var playerImageIndex = playerDataHeaders.indexOf('Player Image');
    var slateTypeIndex = playerDataHeaders.indexOf('Slate Type');
    var roleIndex = playerDataHeaders.indexOf('Slate Header');
    var dateIndex = playerDataHeaders.indexOf('Date');
    var pdGameStartTimeIndex = playerDataHeaders.indexOf('Game Start Time');
    
    if (pdPlayerNameIndex === -1 || slateTypeIndex === -1 || roleIndex === -1 || dateIndex === -1) {
      throw new Error("Required headers 'Player Name', 'Slate Type', 'Slate Header', or 'Date' not found in DRAFTTABLE sheet.");
    }
    
    // Get headers from FINAL PROJECTIONS sheet
    var finalProjLastColumn = finalProjSheet.getLastColumn();
    var finalProjLastRow = finalProjSheet.getLastRow();
    if (finalProjLastColumn < 1 || finalProjLastRow < 1) {
      throw new Error("FINAL PROJECTIONS sheet is empty or has no data.");
    }
    var finalProjHeaders = finalProjSheet.getRange(1, 1, 1, finalProjLastColumn).getValues()[0];
    var fpPlayerNameIndex = finalProjHeaders.indexOf('Player');
    var fpPositionIndex = finalProjHeaders.indexOf('Position');
    var fpTeamIndex = finalProjHeaders.indexOf('Team');
    var dkIndex = finalProjHeaders.indexOf('DraftKings');
    var fpGameStartTimeIndex = finalProjHeaders.indexOf('Game Start Time');
    
    if (fpPlayerNameIndex === -1 || fpPositionIndex === -1 || fpTeamIndex === -1 || dkIndex === -1) {
      throw new Error("Required headers 'Player', 'Position', 'Team', or 'DraftKings' not found in FINAL PROJECTIONS sheet.");
    }
    
    // Read data from sheets
    var combinedData = lastRow > 1 ? combinedSheet.getRange(2, 1, lastRow - 1, lastColumn).getValues() : [];
    var playerData = playerDataLastRow > 1 ? playerDataSheet.getRange(2, 1, playerDataLastRow - 1, playerDataLastColumn).getValues() : [];
    var finalProjData = finalProjLastRow > 1 ? finalProjSheet.getRange(2, 1, finalProjLastRow - 1, finalProjLastColumn).getValues() : [];
    
    // Build projections maps from FINAL PROJECTIONS — keyed by player + normalized date
    var playerProjMap = {};
    var dstProjMap = {};
    for (var i = 0; i < finalProjData.length; i++) {
      var row = finalProjData[i];
      var player = row[fpPlayerNameIndex];
      var position = row[fpPositionIndex];
      var team = row[fpTeamIndex];
      var dk = row[dkIndex] ? parseFloat(row[dkIndex]) : 0;
      var gameStartTime = fpGameStartTimeIndex !== -1 ? normalizeDate(row[fpGameStartTimeIndex]) : '';
      
      if (position === 'DST' || position === 'DEF') {
        if (team) {
          var dstKey = team.toUpperCase() + (gameStartTime ? '|' + gameStartTime : '');
          dstProjMap[dstKey] = dk;
          if (gameStartTime) dstProjMap[team.toUpperCase()] = dk;
        }
      } else {
        var key = getPlayerKey(player);
        if (key) {
          if (!playerProjMap[key]) playerProjMap[key] = {};
          playerProjMap[key][gameStartTime || ''] = dk;
        }
      }
    }
    
    // Process Combined data
    var playerStats = {};
    var teamToMatchTitle = {};
    for (var i = 0; i < combinedData.length; i++) {
      var row = combinedData[i];
      var player = row[playerNameIndex];
      var playerKey = getPlayerKey(player);
      if (!playerKey) continue;
      
      var statType = row[statTypeIndex];
      if (!statType || typeof statType !== 'string') continue;
      
      var statTypeLower = statType.toLowerCase().replace(/\s+/g, '');
      var standardizedStatType = statTypeMapping[statTypeLower] || statType;
      var ppLine = row[ppLineIndex] ? parseFloat(row[ppLineIndex]) : NaN;
      var udLine = row[udLineIndex] ? parseFloat(row[udLineIndex]) : NaN;
      if (isNaN(ppLine) && isNaN(udLine)) continue;
      
      var line = isNaN(ppLine) ? udLine : (isNaN(udLine) ? ppLine : (ppLine + udLine) / 2);
      var gameDate = normalizeDate(row[combinedDateIndex]);
      var gameStartTime = row[udStartTimeIndex] || row[ppStartTimeIndex] || '';
      var matchTitle = matchTitleIndex !== -1 ? (row[matchTitleIndex] || '') : '';
      var gameShortTitle = gameShortTitleIndex !== -1 ? (row[gameShortTitleIndex] || '') : '';
      var venueName = venueNameIndex !== -1 ? (row[venueNameIndex] || '') : '';
      var venueType = venueTypeIndex !== -1 ? (row[venueTypeIndex] || '') : '';
      var broadcasts = broadcastsIndex !== -1 ? (row[broadcastsIndex] || '') : '';
      
      if (!playerStats[playerKey]) playerStats[playerKey] = {};
      if (!playerStats[playerKey][gameDate]) {
        playerStats[playerKey][gameDate] = {
          stats: {}, gameStartTime: gameStartTime, matchTitle: matchTitle,
          gameShortTitle: gameShortTitle, venueName: venueName,
          venueType: venueType, broadcasts: broadcasts
        };
      } else {
        if (!playerStats[playerKey][gameDate].matchTitle && matchTitle) playerStats[playerKey][gameDate].matchTitle = matchTitle;
        if (!playerStats[playerKey][gameDate].gameShortTitle && gameShortTitle) playerStats[playerKey][gameDate].gameShortTitle = gameShortTitle;
        if (!playerStats[playerKey][gameDate].venueName && venueName) playerStats[playerKey][gameDate].venueName = venueName;
        if (!playerStats[playerKey][gameDate].venueType && venueType) playerStats[playerKey][gameDate].venueType = venueType;
        if (!playerStats[playerKey][gameDate].broadcasts && broadcasts) playerStats[playerKey][gameDate].broadcasts = broadcasts;
      }
      playerStats[playerKey][gameDate].stats[standardizedStatType] = line;

      if (matchTitle && matchTitle.trim() !== '' && matchTitle.toLowerCase() !== 'n/a') {
        var parts = matchTitle.split(' @ ');
        if (parts.length === 2) {
          var away = parts[0].trim().toUpperCase();
          var home = parts[1].trim().toUpperCase();
          if (!teamToMatchTitle[gameDate]) teamToMatchTitle[gameDate] = {};
          teamToMatchTitle[gameDate][away] = matchTitle;
          teamToMatchTitle[gameDate][home] = matchTitle;
        }
      }
    }
    
    // Process DRAFTTABLE into groups
    var playerGroups = {};
    for (var i = 0; i < playerData.length; i++) {
      var row = playerData[i];
      var player = row[pdPlayerNameIndex];
      var playerKey = getPlayerKey(player);
      if (!playerKey) continue;
      
      var salary = row[salaryIndex] ? parseFloat(row[salaryIndex]) : NaN;
      var draftableId = row[draftableIdIndex];
      var slateType = row[slateTypeIndex];
      var role = row[roleIndex];
      var date = normalizeDate(row[dateIndex]);
      var pdGameStartTime = pdGameStartTimeIndex !== -1 ? (row[pdGameStartTimeIndex] || '') : '';
      
      if (slateType && !isNaN(salary) && salary > 0 && draftableId) {
        var psr = {
          playerKey: playerKey,
          originalName: player,
          position: row[positionIndex],
          team: row[teamIndex],
          playerImage: row[playerImageIndex],
          slateType: slateType,
          date: date,
          role: role,
          salary: salary,
          draftableId: draftableId,
          pdGameStartTime: pdGameStartTime
        };
        var groupKey = playerKey + '|' + date + '|' + slateType + '|' + (role || '');
        if (!playerGroups[groupKey]) playerGroups[groupKey] = [];
        playerGroups[groupKey].push(psr);
      }
    }
    
    // Deduplicate Classic / Main slates by lowest Draftable ID
    // Keep both CPT + FLEX for Showdown
    var playerSlateRoles = [];
    for (var groupKey in playerGroups) {
      var group = playerGroups[groupKey];
      var currentSlateType = group[0].slateType.toLowerCase();
      
      var isShowdown = currentSlateType.includes('showdown');
      
      if (group.length > 1 && !isShowdown) {
        // Classic (or any non-Showdown) → keep only the lowest Draftable ID
        group.sort(function(a, b) {
          return parseInt(a.draftableId) - parseInt(b.draftableId);
        });
        playerSlateRoles.push(group[0]);
      } else {
        // Showdown → keep all (CPT + FLEX)
        for (var j = 0; j < group.length; j++) {
          playerSlateRoles.push(group[j]);
        }
      }
    }
    
    // Define headers
    var headers = [
      'Player Name', 'Position', 'Team', 'Slate Type', 'Date', 'Role', 'Salary', 'Draftable ID',
      'Projected FP', 'Combined FP', 'Value', 'Implied FP',
      'Passing TDs', 'Rushing Yards', 'Receiving Yards', 'Passing Yards', 'Rush+Rec Yards', 'Anytime TD', 'Passing Attempts',
      'Fantasy Score', 'Headshot URL', 'Game Start Time',
      'Match Title (Underdog)', 'Game Short Title (Underdog)', 'Venue Name (Underdog)', 'Venue Type (Underdog)', 'Broadcasts (Underdog)',
      'Game Start Time (DRAFTTABLE)'
    ];
    
    var dataRows = [];
    
    for (var i = 0; i < playerSlateRoles.length; i++) {
      var psr = playerSlateRoles[i];
      var statsKey = psr.playerKey;
      if (!(statsKey in playerStats) && psr.playerKey in nameMapping) {
        statsKey = nameMapping[psr.playerKey];
      }
      
      // Check if we have data that actually matches this exact date
      var hasCombinedData = playerStats[statsKey] && playerStats[statsKey][psr.date];
      
      var statsData = hasCombinedData
        ? playerStats[statsKey][psr.date]
        : { stats: {}, gameStartTime: '', matchTitle: '', gameShortTitle: '', venueName: '', venueType: '', broadcasts: '' };
      
      var stats = statsData.stats;
      var gameStartTime = statsData.gameStartTime || '';
      
      // Prop lines (only from matching date)
      var passingTDs = stats['Passing TDs'] || '';
      var rushingYards = stats['Rushing Yards'] || '';
      var receivingYards = stats['Receiving Yards'] || '';
      var passingYards = stats['Passing Yards'] || '';
      var rushRecYards = stats['Rush+Rec Yards'] || '';
      var anytimeTD = stats['Anytime TD'] || '';
      var passingAttempts = stats['Passing Attempts'] || '';
      var fantasyScore = stats['Fantasy Score'] || '';
      
      // =====================================================
      // DATE-MATCHED Projected FP
      // Tries multiple date formats for hand projections
      // =====================================================
      var fantasyPoints = 0;
      
      var handKeyFull = psr.playerKey + '|' + psr.date;
      var handKeyShort1 = '';
      var handKeyShort2 = '';
      var handKeyShort3 = '';
      
      try {
        var d2 = new Date(psr.date);
        if (!isNaN(d2.getTime())) {
          var m = d2.getMonth() + 1;
          var day = d2.getDate();
          handKeyShort1 = psr.playerKey + '|' + m + '/' + day;
          handKeyShort2 = psr.playerKey + '|' + m + '/' + ('0' + day).slice(-2);
          handKeyShort3 = psr.playerKey + '|' + ('0' + m).slice(-2) + '/' + ('0' + day).slice(-2);
        }
      } catch (e) {}
      
      if (handProjMap[handKeyFull]) {
        fantasyPoints = handProjMap[handKeyFull];
      } else if (handKeyShort1 && handProjMap[handKeyShort1]) {
        fantasyPoints = handProjMap[handKeyShort1];
      } else if (handKeyShort2 && handProjMap[handKeyShort2]) {
        fantasyPoints = handProjMap[handKeyShort2];
      } else if (handKeyShort3 && handProjMap[handKeyShort3]) {
        fantasyPoints = handProjMap[handKeyShort3];
      } else if (hasCombinedData) {
        fantasyPoints = calculateProjectedFPFromProps(stats, psr.position);
      } else {
        if (psr.position === 'DST' || psr.position === 'DEF') {
          var dstKey = psr.team.toUpperCase() + (psr.date ? '|' + psr.date : '');
          fantasyPoints = dstProjMap[dstKey] || 0;
        } else {
          var projMap = playerProjMap[psr.playerKey] || 
                        (nameMapping[psr.playerKey] ? playerProjMap[nameMapping[psr.playerKey]] : null) || {};
          fantasyPoints = projMap[psr.date] || 0;
        }
      }
      
      // Implied FP
      var impliedFP = psr.salary / 1000 * 3;

      // Combined FP
      var fp_combined = 0;
      if (fantasyPoints > 0) {
        var relevantStats = [
          'Passing TDs', 'Rushing Yards', 'Receiving Yards', 'Passing Yards', 'Rush+Rec Yards',
          'Anytime TD', 'Passing Attempts', 'Fantasy Score', 'FG Made', 'PAT Made'
        ];
        var n = relevantStats.filter(function(stat) { return stat in stats; }).length;
        var weight = 0.8 + 0.2 * (n / relevantStats.length);
        fp_combined = weight * fantasyPoints + (1 - weight) * impliedFP;
      } else {
        fp_combined = 0.2 * impliedFP;
      }

      // Value
      var value = fantasyPoints / (psr.salary / 1000);

      // Showdown role cleanup
      var displayRole = psr.role;
      if (psr.slateType.toLowerCase().includes("showdown")) {
        var useMatchTitle = statsData.matchTitle;
        if (!useMatchTitle || useMatchTitle.trim() === '' || useMatchTitle.toLowerCase() === 'n/a') {
          if (teamToMatchTitle[psr.date] && teamToMatchTitle[psr.date][psr.team.toUpperCase()]) {
            useMatchTitle = teamToMatchTitle[psr.date][psr.team.toUpperCase()];
          } else {
            useMatchTitle = '';
          }
        }
        if (useMatchTitle) {
          displayRole = psr.role.replace("( @ )", "(" + useMatchTitle + ")");
        }
      }

      // Build the row
      var row = [
        psr.originalName,
        psr.position,
        psr.team,
        psr.slateType,
        psr.date,
        psr.slateType + " " + displayRole,
        psr.salary.toFixed(0),
        psr.draftableId,
        fantasyPoints.toFixed(2),
        fp_combined.toFixed(2),
        value.toFixed(2),
        impliedFP.toFixed(2),
        passingTDs,
        rushingYards,
        receivingYards,
        passingYards,
        rushRecYards,
        anytimeTD,
        passingAttempts,
        fantasyScore,
        psr.playerImage,
        gameStartTime,
        statsData.matchTitle || '',
        statsData.gameShortTitle || '',
        statsData.venueName || '',
        statsData.venueType || '',
        statsData.broadcasts || '',
        psr.pdGameStartTime
      ];
      dataRows.push(row);
    }
    
    // Sort by Combined FP descending
    dataRows.sort(function(a, b) {
      var fpA = parseFloat(a[9]) || 0;
      var fpB = parseFloat(b[9]) || 0;
      return fpB - fpA;
    });
    
    // Write to sheet
    if (dataRows.length > 0) {
      var maxRows = cheatSheet.getMaxRows();
      var maxCols = cheatSheet.getMaxColumns();
      if (maxRows > 1) {
        cheatSheet.getRange(2, 1, maxRows - 1, maxCols).clearContent();
      }
      
      cheatSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      cheatSheet.getRange(2, 1, dataRows.length, headers.length).setValues(dataRows);
    }
  } catch (e) {
    Logger.log("Error in createCheatSheet: " + e.message);
  }
}
