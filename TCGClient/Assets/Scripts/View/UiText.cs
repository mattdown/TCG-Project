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
    }
}
