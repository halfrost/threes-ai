document.THREE = document.THREE || {};

LEFT = 37;
RIGHT = 39;
UP = 38;
DOWN = 40;

var running = false
var gameover = false
var tileMap = {0: 0, 1: 1, 2: 2, 3: 3, 6: 4, 12: 5, 24: 6, 48: 7, 96: 8, 192: 9, 384: 10, 768: 11, 1536: 12, 3072: 13, 6144: 14, 12288: 15}

function new_game() {

  // Clear out old tiles
  $(".board .tile").remove();
  var tiles = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]];

  // Generate new configuration
  var locs = [];
  var count = 0;
  while (count < 9) {
    var row = Math.floor(Math.random() * 4);
    var col = Math.floor(Math.random() * 4)
    if (!_.where(locs, {row: row, col: col}).length) {
      locs.push({row: row, col: col});
      count++;
    }
  }

  _.each(locs, function(l) {
    tiles[l.row][l.col] = document.THREE.util.random_tile();
  })

  Session.set("tiles", tiles);
  // set score to zero
  $('#score').text(0);
  // Generate new next tile
  Session.set("next_tile", document.THREE.util.random_tile());
  // set auto run to false
  running = false;
  // set gameover to false
  gameover = false;

  // Render new configuration and next tile
  document.THREE.display.render_board();
  document.THREE.display.render_next();
}

function move(e) {
  var direction = e.which;
  var g = generate_new_board(direction);

  // Check if any tiles moved
  if (_.isEmpty(g.moved)) {
    return;
  }

  // Execute the move
  document.THREE.display.animate_move(g, direction);
  Session.set("tiles", g.board);

  // Add in the new tile
  var l = insert_new_tile(g.moved, direction);
  document.THREE.display.animate_new_tile(l, direction);
  var tiles = Session.get("tiles");
  tiles[l.i][l.j] = Session.get("next_tile");
  Session.set("tiles", tiles);

  // Woohoo!
  tick();
}

function auto_move(direction) {

  var g = generate_new_board(direction);

  // Check if any tiles moved
  if (_.isEmpty(g.moved)) {
    return;
  }

  // Execute the move
  document.THREE.display.animate_move(g, direction);
  Session.set("tiles", g.board);

  // Add in the new tile
  var l = insert_new_tile(g.moved, direction);
  document.THREE.display.animate_new_tile(l, direction);
  var tiles = Session.get("tiles");
  tiles[l.i][l.j] = Session.get("next_tile");
  Session.set("tiles", tiles);

  // Woohoo!
  tick();
}

function generate_new_board(direction) {
  var tiles = Session.get("tiles");
  var board = JSON.parse(JSON.stringify(tiles));
  var moved = [];
  var changed = [];

  var attempt_tile_move = function(i, j, i_pr, j_pr) {
    // Empty space
    if (board[i][j] === 0) {
      return;
    }

    // Twins
    if (board[i][j] === board[i_pr][j_pr]) {
      // Not actually twins
      if (board[i][j] === 1 || board[i][j] === 2) {
        return;
      }

      // Okay actually twins
      board[i][j] = 0;
      board[i_pr][j_pr] *= 2;
      moved.push({i: i, j: j, t: board[i_pr][j_pr]});
    }

    // Not twins
    else {
      // Move to empty space
      if (board[i_pr][j_pr] === 0) {
        board[i_pr][j_pr] = board[i][j];
        board[i][j] = 0;
        moved.push({i: i, j: j, t: board[i_pr][j_pr]});
      }

      // 1 + 2 = 3
      else if ((board[i][j] === 1 && board[i_pr][j_pr] === 2) ||
               (board[i][j] === 2 && board[i_pr][j_pr] === 1)) {
        board[i_pr][j_pr] = 3;
        board[i][j] = 0;
        moved.push({i: i, j: j, t: board[i_pr][j_pr]});
      }
    }
  }

  switch(direction) {
    case LEFT:
      for (var i = 0; i <= 3; i++) {
        for (var j = 0; j <= 3; j++) {
          if (j === 0) {
            continue;
          }
          attempt_tile_move(i, j, i, j - 1);
        }
      }
    break;

    case RIGHT:
      for (var i = 0; i <= 3; i++) {
        for (var j = 3; j >= 0; j--) {
          if (j === 3) {
            continue;
          }
          attempt_tile_move(i, j, i, j + 1);
        }
      }
    break;

    case UP:
      for (var j = 0; j <= 3; j++) {
        for (var i = 0; i <= 3; i++) {
          if (i === 0) {
            continue;
          }
          attempt_tile_move(i, j, i - 1, j);
        }
      }
    break;

    case DOWN:
      for (var j = 0; j <= 3; j++) {
        for (var i = 3; i >= 0; i--) {
          if (i === 3) {
            continue;
          }
          attempt_tile_move(i, j, i + 1, j);
        }
      }
    break;
  }

  return {board: board, moved: moved};
}

function insert_new_tile(moved, direction) {
  var tiles = Session.get("tiles");
  var locs = [];

  switch(direction) {
    case LEFT: // Right column
      var j = 3;
      var rows = _.uniq(_.pluck(moved, "i"));

      _.each(rows, function(i) {
        if (tiles[i][j] === 0) {
          locs.push({i: i, j: j});
        }
      });
    break;

    case RIGHT: // Left column
      var j = 0;
      var rows = _.uniq(_.pluck(moved, "i"));

      _.each(rows, function(i) {
        if (tiles[i][j] === 0) {
          locs.push({i: i, j: j});
        }
      });
    break;

    case UP: // Bottom column
      var i = 3;
      var cols = _.uniq(_.pluck(moved, "j"));

      _.each(cols, function(j) {
        if (tiles[i][j] === 0) {
          locs.push({i: i, j: j});
        }
      });
    break;

    case DOWN: // Top column
      var i = 0;
      var cols = _.uniq(_.pluck(moved, "j"));

      _.each(cols, function(j) {
        if (tiles[i][j] === 0) {
          locs.push({i: i, j: j});
        }
      });
    break;
  }
  return _.sample(locs);
}

function tick() {
  var tiles = Session.get("tiles");

  // Check for empty spaces
  var tile_list = _.flatten(tiles);
  if (_.contains(tile_list, 0)) {
    next();
    return;
  }

  // Check for moves in every direction
  var directions = [LEFT, RIGHT, UP, DOWN];
  for (var d = 0; d <= 3; d++) {
    var g = generate_new_board(directions[d]);
    if (!_.isEmpty(g.moved)) {
      next();
      return;
    }
  }

  // Oops, no empty spaces or moves left
  gameover = true;
  setTimeout(lost, 500);
}

function next() {
  var next_tile = document.THREE.util.random_tile();
  Session.set("next_tile", next_tile);
  document.THREE.display.render_next();
  document.THREE.display.render_score(getScore())
}

function getScore() {
  var tiles = Session.get("tiles");

  var score_tile = function(t) {
    score = Math.pow(3, (Math.log(t / 3) / Math.log(2) + 1));
    return Math.floor(score);
  }

  var total = _.reduce(_.flatten(tiles), function(acc, t) {
    return acc + ((t != 1 && t != 2) ? score_tile(t) : 0);
  }, 0);

  return total
}

function lost() {
  document.THREE.display.render_score(getScore())
  document.THREE.display.render_lost(getScore());
}

function auto_run(){
  if(running){
    running=false;
  }else{
    running=true;
    sendMessage(false);
  }
  updateButton(10)
}

function game_hint(){
  sendMessage(true)
}

function get_send_data(){
  var tiles = Session.get("tiles");
  var nt = Session.get("next_tile");
  var board = JSON.parse(JSON.stringify(tiles));

  var bboard = new Array();
  bboard[0] = new Array();
  bboard[1] = new Array();
  bboard[2] = new Array();
  bboard[3] = new Array();
  for (var i = 0; i < board[0].length; i++) {
    bboard[0][i] = tileMap[board[0][i]]
  }
  for (var i = 0; i < board[1].length; i++) {
    bboard[1][i] = tileMap[board[1][i]]
  }
  for (var i = 0; i < board[2].length; i++) {
    bboard[2][i] = tileMap[board[2][i]]
  }
  for (var i = 0; i < board[3].length; i++) {
    bboard[3][i] = tileMap[board[3][i]]
  }

  var data = {"data":bboard,"next":nt}
  return data
}

function sendMessage(isHint) {
  var self=this;

  var data = get_send_data()

  if (window["WebSocket"]) {
    if(!self.ws){
      var protocol="ws://";
      if(window.location.protocol=="https:"){
        protocol="wss://";
      }
      self.ws = new WebSocket(protocol+window.location.hostname+":9000"+"/compute");
      self.ws.onopen = function(evt) {
        if(!isHint){
          running=true;
        }
        console.log("Connection open ...");
        self.ws.send(JSON.stringify({
          // data: '网页开始send数据啦'
          data: data["data"],
          next: data["next"]
        }));
        updateButton(10);
      };

      self.ws.onmessage = function(evt) {
        var resp=JSON.parse(evt.data);
        // console.log( "Received Message: " + resp.dire);
        updateButton(resp.dire)
        if(run(resp.dire)){
          var nextData = get_send_data()
          self.ws.send(JSON.stringify({
            data: nextData["data"],
            next: nextData["next"]
          }));
        }
      };

      self.ws.onclose = function(evt) {
        running=false;
        console.log("Connection closed.");
        updateButton(10);
      };
    }else{
      self.ws.send(JSON.stringify({
        data: data["data"],
        next: data["next"]
      }));
      updateButton(10);
    }
  } else {
    var item = document.createElement("div");
    item.innerHTML = "<b>Your browser does not support WebSockets.</b>";
    appendLog(item);
  }
}

function updateButton(dire) {
  switch (dire) {
    case 0:
      $('#gamehint').text('↑');
      break;
    case 1:
      $('#gamehint').text('↓');
      break;
    case 2:
      $('#gamehint').text('←');
      break;
    case 3:
      $('#gamehint').text('→');
      break;
  }
  if(!running){
    $('#auto-run').text('AI');
    if (dire == 10) {
      $('#gamehint').text('hint');
    }
  }else{
    $('#auto-run').text('stop');
  }
};

// moves continuously until game is over
function run(dire) {
  if(!running){
    return
  }
  if(gameover){
    running=false;
    updateButton(10)
    return
  }

  switch (dire) {
    case 0:
      auto_move(UP)
      break;
    case 1:
      auto_move(DOWN)
      break;
    case 2:
      auto_move(LEFT)
      break;
    case 3:
      auto_move(RIGHT)
      break;
  }
  return running && !gameover
};

document.THREE.game = {
  new_game: new_game,
  move: move,
  generate_new_board: generate_new_board,
  insert_new_tile: insert_new_tile,
  tick: tick,
  next: next,
  lost: lost,
  auto_run: auto_run,
  game_hint: game_hint
};
