document.THREE = document.THREE || {};

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

document.THREE.game = {
  new_game: new_game,
  move: move,
  generate_new_board: generate_new_board,
  insert_new_tile: insert_new_tile,
  tick: tick,
  next: next,
  lost: lost
};
