document.THREE = document.THREE || {};

// ... is this supposed to be here?
Session.set("deck", [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]);
Session.set("current_deck", []);

function random_tile() {
  var deck = Session.get("deck");
  var current_deck = Session.get("current_deck");
  var tiles = Session.get("tiles");

  // Bonus draw
  var bonus = _.some(_.flatten(tiles), function(t) {return (t >= 48);} )
  if (bonus && (Math.random() <= 1/21)) {
    var highest = _.max(_.flatten(tiles));
    var size = Math.log(highest / 3) / Math.log(2) - 3; // Help what is math
    var bonus_deck = _(size).times(function(n) {
      return 6 * Math.pow(2, n);
    });

    var t = _.sample(bonus_deck);
    return t;
  }

  // Normal draw
  if (_.isEmpty(current_deck)) {
    current_deck = _.shuffle(deck);
  }

  var t = _.first(current_deck);
  current_deck = _.rest(current_deck);

  Session.set("deck", deck);
  Session.set("current_deck", current_deck);
  return t;
}

// Helper to compute tile class
function tile_class(tile) {
  if (tile === 1) {
    return "blue";
  }
  else if (tile === 2) {
    return "red";
  }
  else if (tile == 3) {
    return "number";
  }
  else {
    return "bonus";
  }
}

document.THREE.util = {
  random_tile: random_tile,
  tile_class: tile_class
};