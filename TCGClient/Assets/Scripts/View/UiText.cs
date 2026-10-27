namespace Tcg.View
{
    /// <summary>
    /// The client's own chrome strings. Game terms and card names come from the server; these are
    /// the few labels the mockup adds around them, kept here so the game can be renamed in one place.
    /// </summary>
    public static class UiText
    {
        public const string You = "You";
        public const string YouAvatar = "ME";
        public const string Deck = "Deck";
        public const string Hand = "Hand";
        public const string Turn = "TURN";
        public const string NewGame = "NEW GAME";
        public const string Waiting = "WAIT";
        public const string Connecting = "Connecting to the game server…";
        public const string YouWin = "You win!";
        public const string YouLose = "You lose";
        public const string Draw = "Draw";

        // Drop zones: {0} is the number from the action's preview.
        public const string DropToPlay = "Drop to play · {0} mana";
        public const string Defeated = "Defeated";
        public const string Takes = "Takes {0}";
        public const string Frozen = "Frozen";

        // Inspect.
        public const string TapToClose = "Tap anywhere to close";
        public const string PlayButton = "PLAY · {0}";
        public const string ButtonsNote = "Buttons do the same as dragging. They’re greyed out when the action isn’t allowed.";
        public const string YourUnit = "Your unit";
        public const string OpponentsUnit = "Opponent’s unit";
        public const string InYourHand = "In your hand";
        public const string Exhausted = "Exhausted";
        public const string Fresh = "Fresh";
        public const string DamageChip = "Damage {0}";
        public const string HealthTitle = "Health {0} of {1}";
        public const string HealthText = "This unit has taken {0} damage. The heart shows the health it has left.";

        // Abilities.
        public const string ChooseHint = "Tap a highlighted card";
        public const string OpponentChoosing = "{0} is choosing";
        public const string CardTextTitle = "Card text";
        public const string FrozenChip = "Frozen: can't attack next turn";
        public const string HiddenChip = "Hidden until it attacks";

        // Dev scenario panel.
        public const string DevButton = "DEV";
        public const string DevTitle = "Start a scenario";
        public const string DevHelp = "One key per line or separated by ;  Keys: hand, play, opponent_play, opponent_hand (card IDs, comma-separated; add \"exhausted\" or \"damage=N\" after an ID in play), mana, opponent_mana, health, opponent_health, seed.";
        public const string DevStart = "START";
        public const string DevClose = "CLOSE";
        public const string DevDefault = "mana: 5\nopponent_health: 10\nseed: 1";

        // Help screen. Keyword rules and class names come from the server's card_set.
        public const string HelpTitle = "How to read a card";
        public const string HelpKeywords = "Keywords";
        public const string HelpClasses = "Classes";
        public const string HelpCost = "Cost";
        public const string HelpCostText = "Mana to play it";
        public const string HelpColour = "Class colour";
        public const string HelpColourText = "The frame shows its habitat";
        public const string HelpName = "Name";
        public const string HelpNameText = "and its subtitle";
        public const string HelpRules = "Rules text";
        public const string HelpRulesText = "Keywords first, then what it does";
        public const string HelpAttack = "Attack";
        public const string HelpAttackText = "Damage it deals when it fights";
        public const string HelpHealth = "Health";
        public const string HelpHealthText = "Damage it can take. Red means hurt";
        public const string HelpJob = "Job";
        public const string HelpJobText = "Other cards can count or boost a job";
        // {0}, {1}: the raised / lowered stat colours; {2}: the Charge keyword's name.
        public const string HelpNoteStats = "<color=#{0}><b>Green</b></color> numbers are raised, <color=#{1}><b>red</b></color> are lowered.";
        public const string HelpNoteFresh = "A unit can’t attack the turn it’s played (unless it has {0}).";
        public const string HelpNoteFrozen = "<color=#BFE9FF><b>❄ Frozen</b></color> units skip their next attack.";

        // Mulligan and game over.
        public const string MulliganTitle = "Choose cards to put back";
        public const string MulliganText = "Tap the cards to put back (tap again to keep one). You draw a new card for each.";
        public const string PutBack = "PUT BACK";
        public const string Keep = "KEEP";
        public const string FinalScore = "{0} {1} · {2} {3}";
    }
}
