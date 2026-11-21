@IsTest
private class ServiceTicketSlaServiceTest {

    @IsTest
    static void dueTimeFollowsPriority() {
        Datetime opened = Datetime.newInstance(2026, 11, 20, 9, 0, 0);
        System.assertEquals(opened.addHours(4), ServiceTicketSlaService.calculateDue('Critical', opened), 'Critical is 4 hours');
        System.assertEquals(opened.addHours(8), ServiceTicketSlaService.calculateDue('High', opened), 'High is 8 hours');
        System.assertEquals(opened.addHours(24), ServiceTicketSlaService.calculateDue('Normal', opened), 'Normal is 24 hours');
        System.assertEquals(opened.addHours(72), ServiceTicketSlaService.calculateDue('Low', opened), 'Low is 72 hours');
    }

    @IsTest
    static void blankOrUnknownPriorityUsesNormal() {
        Datetime opened = Datetime.newInstance(2026, 11, 20, 9, 0, 0);
        System.assertEquals(opened.addHours(24), ServiceTicketSlaService.calculateDue(null, opened), 'Blank priority');
        System.assertEquals(opened.addHours(24), ServiceTicketSlaService.calculateDue('Urgent', opened), 'Unknown priority');
    }

    @IsTest
    static void blankOpenedTimeGivesNoDueTime() {
        System.assertEquals(null, ServiceTicketSlaService.calculateDue('High', null), 'No opened time, no due time');
    }

    @IsTest
    static void insertSetsOpenedAndDueTimes() {
        Service_Ticket__c ticket = new Service_Ticket__c(Priority__c = 'High');
        insert ticket;
        Service_Ticket__c saved = [SELECT Opened_At__c, Sla_Due_At__c FROM Service_Ticket__c WHERE Id = :ticket.Id];
        System.assertNotEquals(null, saved.Opened_At__c, 'Opened time is stamped');
        System.assertEquals(saved.Opened_At__c.addHours(8), saved.Sla_Due_At__c, 'High priority due in 8 hours');
    }

    @IsTest
    static void bulkInsertOf200Works() {
        List<Service_Ticket__c> tickets = new List<Service_Ticket__c>();
        for (Integer i = 0; i < 200; i++) {
            tickets.add(new Service_Ticket__c(Priority__c = 'Low'));
        }
        Test.startTest();
        insert tickets;
        Test.stopTest();
        Integer withDue = [SELECT COUNT() FROM Service_Ticket__c WHERE Sla_Due_At__c != null];
        System.assertEquals(200, withDue, 'Every ticket gets a due time');
    }

    @IsTest
    static void priorityChangeRecalculatesDueTime() {
        Service_Ticket__c ticket = new Service_Ticket__c(Priority__c = 'Low');
        insert ticket;
        ticket.Priority__c = 'Critical';
        update ticket;
        Service_Ticket__c saved = [SELECT Opened_At__c, Sla_Due_At__c FROM Service_Ticket__c WHERE Id = :ticket.Id];
        System.assertEquals(saved.Opened_At__c.addHours(4), saved.Sla_Due_At__c, 'Critical due in 4 hours');
    }

    @IsTest
    static void resolvingOnTimeMeetsTheSla() {
        Service_Ticket__c ticket = new Service_Ticket__c(Priority__c = 'Normal', Status__c = 'Open');
        insert ticket;
        ticket.Status__c = 'Resolved';
        update ticket;
        Service_Ticket__c saved = [SELECT Resolved_At__c, Sla_Met__c FROM Service_Ticket__c WHERE Id = :ticket.Id];
        System.assertNotEquals(null, saved.Resolved_At__c, 'Resolved time is stamped');
        System.assertEquals(true, saved.Sla_Met__c, 'Resolved at once, so the SLA is met');
    }

    @IsTest
    static void resolvingLateMissesTheSla() {
        Service_Ticket__c ticket = new Service_Ticket__c(
            Priority__c = 'Critical',
            Status__c = 'Open',
            Opened_At__c = System.now().addHours(-10)
        );
        insert ticket;
        ticket.Status__c = 'Resolved';
        update ticket;
        Service_Ticket__c saved = [SELECT Sla_Met__c FROM Service_Ticket__c WHERE Id = :ticket.Id];
        System.assertEquals(false, saved.Sla_Met__c, 'Ten hours is past the 4 hour limit');
    }
}
