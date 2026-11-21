@IsTest(SeeAllData=true)
private class BadTicketHandlerTest {
    @IsTest
    static void runs() {
        BadTicketHandler.run(new List<Service_Ticket__c>());
    }
}
