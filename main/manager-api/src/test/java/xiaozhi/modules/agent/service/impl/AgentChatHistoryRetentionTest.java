package xiaozhi.modules.agent.service.impl;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Date;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import xiaozhi.modules.agent.dao.AiAgentChatHistoryDao;
import xiaozhi.modules.agent.entity.AgentChatHistoryEntity;
import xiaozhi.modules.agent.service.AgentChatTitleService;

class AgentChatHistoryRetentionTest {
    @Test
    void deletingExpiredTextAlsoDeletesItsAudio() {
        AiAgentChatHistoryDao dao = mock(AiAgentChatHistoryDao.class);
        AgentChatHistoryServiceImpl service = new AgentChatHistoryServiceImpl(
                mock(AgentChatTitleService.class));
        ReflectionTestUtils.setField(service, "baseMapper", dao);
        AgentChatHistoryEntity old = AgentChatHistoryEntity.builder()
                .audioId("audio-old")
                .build();
        when(dao.selectList(any())).thenReturn(List.of(old));

        service.deleteBefore("agent-1", new Date());

        verify(dao).deleteAudioByIds(List.of("audio-old"));
        verify(dao).delete(any());
    }
}
