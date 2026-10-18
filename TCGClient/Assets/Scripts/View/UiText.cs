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
        public const string DropToPlay = "Drop to play · {0} energy";
        public const string DropToAddEnergy = "Drop to add as energy · once per turn";
        public const string DropToScore = "Drop to score · +{0} VP";
        public const string Defeated = "Defeated";
        public const string Takes = "Takes {0}";
        public const string CantReady = "Can't ready";
        public const string Barred = "Can't score or ⟳";

        // Inspect.
        public const string TapToClose = "Tap anywhere to close";
        public const string PlayButton = "PLAY · {0}";
        public const string AddEnergyButton = "ADD ENERGY";
        public const string ButtonsNote = "Buttons do the same as dragging. They’re greyed out when the action isn’t allowed.";
        public const string YourUnit = "Your unit";
        public const string OpponentsUnit = "Opponent’s unit";
        public const string InYourHand = "In your hand";
        public const string Exhausted = "Exhausted";
        public const string Fresh = "Fresh";
        public const string DamageChip = "Damage {0}";
        public const string EnergySourceTitle = "Energy source";
        public const string EnergySourceText = "The gold rim round the cost means this card can be added to your energy instead of played.";
        public const string NotEnergySourceTitle = "Not an energy source";
        public const string NotEnergySourceText = "The dark rim round the cost means this card can only be played, not added as energy.";
        public const string HealthTitle = "Health {0} of {1}";
        public const string HealthText = "This unit has taken {0} damage. The heart shows the health it has left.";

        // Abilities.
        public const string ChooseHint = "Tap a highlighted card";
        public const string OpponentChoosing = "{0} is choosing";
        public const string CardTextTitle = "Card text";
        public const string CantReadyChip = "Can't ready next turn";
        public const string BarredChip = "Can't score or ⟳ this turn";

        // Dev scenario panel.
        public const string DevButton = "DEV";
        public const string DevTitle = "Start a scenario";
        public const string DevHelp = "One key per line or separated by ;  Keys: hand, play, opponent_play, opponent_hand (card IDs, comma-separated; add \"exhausted\" or \"damage=N\" after an ID in play), energy, opponent_energy, vp, opponent_vp, seed.";
        public const string DevStart = "START";
        public const string DevClose = "CLOSE";
        public const string DevDefault = "play: C1-024\nopponent_play: C1-018, C1-036\nenergy: 2";

        // Mulligan and game over.
        public const string MulliganTitle = "Choose cards to put back";
        public const string MulliganText = "Tap the cards to put back (tap again to keep one). You draw a new card for each.";
        public const string PutBack = "PUT BACK";
        public const string Keep = "KEEP";
        public const string FinalScore = "{0} {1} · {2} {3}";
    }
}
