document.THREE = document.THREE || {};

function render_board() {
  var tiles = Session.get("tiles");
  for (var i = 0; i <= 3; i++) {
    for (var j = 0; j <= 3; j++) {
      var t = tiles[i][j];

      if (tiles[i][j] != 0) {
        var block = Template.tile({row: i, col: j, tile: t});
        block = $(block).addClass(document.THREE.util.tile_class(t));

        // (Here there be magic numbers)
        block = $(block).css({
          left: 22 + (j * 92),
          top: 22 + (i * 130)
        });

        $(".board").append(block);
      }
    }
  }
}

function render_next() {
  var next_tile = Session.get("next_tile");
  $(".next .tile").removeClass("red")
                  .removeClass("blue")
                  .removeClass("number")
                  .removeClass("bonus");
  $(".next .tile").addClass(document.THREE.util.tile_class(next_tile));
}

function render_lost(total) {
  var tweet = "I scored " + total + " on %23threesjs! %5E_____%5E";
  var fb_status = "I scored " + total + " on #threesjs! ^_____^";

  var overlay = $("<div/>", {class: "overlay"});
  var endgame = Template.endgame({score: total, tweet: tweet});
  overlay.append(endgame);

  $("body").append(overlay);
  overlay.fadeIn(200);

  // Facebook sharing
  $("#share-facebook").click(function(e) {
    e.preventDefault();
    FB.ui({
      method: "feed",
      link: "http://threesjs.com",
      caption: fb_status,
    }, function(response){});
  });

  // Close modal
  $("body").click(function(e) {
    if (!$(e.target).closest(".endgame").length) {
      overlay.remove();
    }
  });

  $(window).on("keydown", function(e) {
    if (e.keyCode === 13) { // Enter
      overlay.remove();
    }
  });
}

function animate_move(obj, direction) {
  var board = obj.board;
  var moved = obj.moved;

  var movement;

  switch(direction) {
    case LEFT:
      movement = function(c) {
        return {top: c.top, left: c.left - 92};
      }
      coords = function(i, j) {
        return String(i) + String(j - 1);
      }
    break;

    case RIGHT:
      movement = function(c) {
        return {top: c.top, left: c.left + 92};
      }
      coords = function(i, j) {
        return String(i) + String(j + 1);
      }
    break;

    case UP:
      movement = function(c) {
        return {top: c.top - 130, left: c.left};
      }
      coords = function(i, j) {
        return String(i - 1) + String(j);
      }
    break;

    case DOWN:
      movement = function(c) {
        return {top: c.top + 130, left: c.left};
      }
      coords = function(i, j) {
        return String(i + 1) + String(j);
      }
    break;
  }

  $(".tile").css("zIndex", 10);

  _.each(moved, function(t) {
    var el = $("[data-coords=" + String(t.i) + String(t.j) + "]");

    var old_coords = {top: parseInt(el.css("top")), left: parseInt(el.css("left"))};
    var new_coords = movement(old_coords);

    el.css("zIndex", 100);
    el.animate({
      top: new_coords.top,
      left: new_coords.left
    }, 200, "easeOutQuart", function() {
      $("[data-coords=" + coords(t.i, t.j) + "]").remove();
      el.attr("data-coords", coords(t.i, t.j));
      el.removeClass("blue");
      el.removeClass("red");
      el.removeClass("number");
      el.addClass(document.THREE.util.tile_class(t.t));
      el.html(t.t);

      // el.effect("bounce", {distance: 30, times: 3});
    });
  });
}

function animate_new_tile(coords, direction) {
  var next_tile = Session.get("next_tile");
  var origin;

  switch(direction) {
    case LEFT:
      origin = function(top, left) {
        return {top: top, left: left + 92};
      }
    break;

    case RIGHT:
      origin = function(top, left) {
        return {top: top, left: left - 92};
      }
    break;

    case UP:
      origin = function(top, left) {
        return {top: top + 130, left: left};
      }
    break;

    case DOWN:
      origin = function(top, left) {
        return {top: top - 130, left: left};
      }
    break;
  }

  var block = Template.tile({row: coords.i, col: coords.j, tile: next_tile});
  block = $(block).addClass(document.THREE.util.tile_class(next_tile));

  var top = 22 + (coords.i * 130);
  var left = 22 + (coords.j * 92);
  var origins = origin(top, left);

  block.css({
    left: origins.left,
    top: origins.top
  });
  $(".board").append(block);

  block.animate({
    top: top,
    left: left
  }, 200, "easeOutQuart");
}

document.THREE.display = {
  render_board: render_board,
  render_next: render_next,
  render_lost: render_lost,
  animate_move: animate_move,
  animate_new_tile: animate_new_tile
};