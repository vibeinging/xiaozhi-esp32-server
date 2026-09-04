package xiaozhi.modules.childsafety.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

@Data
public class ChildSafetySettingDTO {
    @NotNull
    private Boolean enabled;

    @NotBlank
    @Pattern(regexp = "^(?:[01]\\d|2[0-3]):[0-5]\\d$")
    private String reviewTime = "22:00";

    @NotBlank
    private String timezone = "Asia/Shanghai";

    @NotNull
    @Min(1)
    @Max(30)
    private Integer chatRetentionDays = 7;

    @NotNull
    @Min(30)
    @Max(365)
    private Integer reportRetentionDays = 90;
}
